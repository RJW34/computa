# ABSO-Tray.ps1 - System tray for computa with Dark Theme (Modernized)
# Memory: ~25-35MB | CPU: Near-zero when idle
# Left-click shows profile menu, applies via CLI, monitors game lifecycle
# Features: Dynamic icons, favorites, search, progress overlay, hotkeys, settings

param(
    [switch]$Hidden,
    [string]$RestartToken = ""
)

# Cold-start wall clock: started at script entry, stopped right before
# Application.Run so we can log total time-to-ready and catch regressions.
$script:ColdStartStopwatch = [System.Diagnostics.Stopwatch]::StartNew()

# ============================================================================
# ADMIN ELEVATION CHECK
# ============================================================================

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    $scriptPath = $PSCommandPath
    try {
        $elevationArgs = @(
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-File", "`"$scriptPath`"",
            "-Hidden"
        )
        if (-not [string]::IsNullOrWhiteSpace($RestartToken)) {
            $elevationArgs += @("-RestartToken", "`"$RestartToken`"")
        }
        Start-Process powershell.exe -ArgumentList ($elevationArgs -join " ") -Verb RunAs -WindowStyle Hidden
    }
    catch {
        Add-Type -AssemblyName System.Windows.Forms
        [System.Windows.Forms.MessageBox]::Show(
            "computa Tray requires administrator privileges to apply profiles.`n`nPlease run as Administrator.",
            "computa",
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
. (Join-Path $script:ScriptDir "ABSO-Theme.ps1")
. (Join-Path $script:ScriptDir "ABSO-ThemePack.ps1")
. (Join-Path $script:ScriptDir "ABSO-Icons.ps1")
. (Join-Path $script:ScriptDir "ABSO-Notifications.ps1")
. (Join-Path $script:ScriptDir "ABSO-Settings.ps1")
. (Join-Path $script:ScriptDir "ABSO-StartupState.ps1")
. (Join-Path $script:ScriptDir "ABSO-QuickPanel.ps1")

# ============================================================================
# SOUND EFFECTS
# ============================================================================

# Sound cues resolve through the active theme pack (ABSO-ThemePack.ps1):
# each event maps to a media file, a Windows system sound, or silence. The
# built-in defaults are system sounds, so no media files need to ship.
$script:MediaPlayer = $null
$script:RestartSoundMarkerMaxAgeSeconds = 180
try {
    $restartMarkerRoot = Join-Path ([Environment]::GetFolderPath("LocalApplicationData")) "AdaptiveBattleStationOptimizer"
}
catch {
    $restartMarkerRoot = $env:TEMP
}
$script:RestartSoundMarkerFile = Join-Path $restartMarkerRoot "tray-restart-pending.json"
$script:RestartToken = if ([string]::IsNullOrWhiteSpace($RestartToken)) { "" } else { $RestartToken.Trim() }

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
        $cue = Get-ThemeSoundCue -SoundEvent "success"
        if ($cue.Type -eq "file") {
            Play-SoundFile -FilePath $cue.Path -Volume $script:TrayConfig.soundVolume
            Write-TrayLog "Playing success sound"
        }
        elseif ($cue.Type -eq "system") {
            Play-SystemSoundCue -Name $cue.Name | Out-Null
            Write-TrayLog "Playing success system cue ($($cue.Name))"
        }
    }
    catch {
        Write-TrayLog "Failed to play sound: $($_.Exception.Message)" -Level "WARN"
    }
}

function Play-FailSound {
    try {
        if (-not $script:TrayConfig.soundEnabled) { return }
        $cue = Get-ThemeSoundCue -SoundEvent "fail"
        if ($cue.Type -eq "file") {
            Play-SoundFile -FilePath $cue.Path -Volume ([Math]::Min(1.0, $script:TrayConfig.soundVolume * 3))
            Write-TrayLog "Playing fail sound"
        }
        elseif ($cue.Type -eq "system") {
            Play-SystemSoundCue -Name $cue.Name | Out-Null
            Write-TrayLog "Playing fail system cue ($($cue.Name))"
        }
    }
    catch {
        Write-TrayLog "Failed to play fail sound: $($_.Exception.Message)" -Level "WARN"
    }
}

function Play-VrrWarningSound {
    try {
        if (-not $script:TrayConfig.soundEnabled) { return }
        $cue = Get-ThemeSoundCue -SoundEvent "vrrWarning"
        if ($cue.Type -eq "file") {
            Play-SoundFile -FilePath $cue.Path -Volume ([Math]::Min(1.0, $script:TrayConfig.soundVolume * 2.5))
            Write-TrayLog "Playing VRR warning sound"
        }
        elseif ($cue.Type -eq "system") {
            Play-SystemSoundCue -Name $cue.Name | Out-Null
            Write-TrayLog "Playing VRR warning system cue ($($cue.Name))"
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
            Write-TrayLog "Restart sound skipped (tray audio cues disabled)"
            return
        }

        $cue = Get-ThemeSoundCue -SoundEvent "restart"
        if ($cue.Type -eq "none") {
            Write-TrayLog "Restart sound skipped (theme silences it)"
            return
        }
        if ($cue.Type -eq "system") {
            Play-SystemSoundCue -Name $cue.Name | Out-Null
            Write-TrayLog "Playing restart system cue ($($cue.Name))"
            return
        }
        $restartSoundPath = $cue.Path

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
        $openRc = [AbsoMci]::mciSendStringW("open `"$restartSoundPath`" type mpegvideo alias $alias", $errBuf, $errBuf.Capacity, [IntPtr]::Zero)
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
            $fallbackCue = Get-ThemeSoundCue -SoundEvent "restart"
            if ($fallbackCue.Type -ne "file") { return }
            Play-SoundFile -FilePath $fallbackCue.Path -Volume $script:TrayConfig.soundVolume
            Start-Sleep -Milliseconds 350
            Write-TrayLog "Restart sound fallback played via MediaPlayer"
        }
        catch {
            Write-TrayLog "Restart sound fallback failed: $($_.Exception.Message)" -Level "WARN"
        }
    }
}

function Set-RestartSuccessSoundMarker {
    param([string]$RestartToken)

    try {
        if (-not $script:RestartSoundMarkerFile) { return }
        if ([string]::IsNullOrWhiteSpace($RestartToken)) {
            Write-TrayLog "Restart success-sound marker skipped: missing restart token" -Level "WARN"
            return
        }

        $dir = Split-Path -Parent $script:RestartSoundMarkerFile
        if ($dir -and -not (Test-Path $dir)) {
            New-Item -Path $dir -ItemType Directory -Force | Out-Null
        }

        $payload = [ordered]@{
            requested_at = (Get-Date).ToString("o")
            requested_pid = $PID
            source = "restart_menu"
            restart_token = $RestartToken.Trim()
        }
        $payload | ConvertTo-Json -Depth 3 | Set-Content -Path $script:RestartSoundMarkerFile -Encoding UTF8
        Write-TrayLog "Restart success-sound marker written"
    }
    catch {
        Write-TrayLog "Failed to write restart success-sound marker: $($_.Exception.Message)" -Level "WARN"
    }
}

function Clear-RestartSuccessSoundMarker {
    try {
        if ($script:RestartSoundMarkerFile -and (Test-Path $script:RestartSoundMarkerFile)) {
            Remove-Item -Path $script:RestartSoundMarkerFile -Force -ErrorAction SilentlyContinue
        }
    }
    catch {
        Write-TrayLog "Failed to clear restart success-sound marker: $($_.Exception.Message)" -Level "WARN"
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

        $markerToken = if ($marker -and $marker.restart_token) { "$($marker.restart_token)".Trim() } else { "" }
        if (
            [string]::IsNullOrWhiteSpace($markerToken) -or
            [string]::IsNullOrWhiteSpace($script:RestartToken) -or
            $markerToken -ne $script:RestartToken
        ) {
            Write-TrayLog "Restart success-sound marker ignored: token mismatch or missing"
            Remove-Item -Path $script:RestartSoundMarkerFile -Force -ErrorAction SilentlyContinue
            return
        }

        # Consume marker first to avoid replay if audio fails.
        Remove-Item -Path $script:RestartSoundMarkerFile -Force -ErrorAction SilentlyContinue
        Write-TrayLog "Restart marker consumed; playing restart success sound"
        $script:RestartToken = ""
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
        $Message -match "Enable G-SYNC in NVIDIA Control Panel" -or
        $Message -match "strict G-SYNC path is blocked" -or
        $Message -match "fullscreen-exclusive profile requires overlays" -or
        $Message -match "primary display .* does not report confirmed VRR/G-SYNC support"
    )
}

function Add-UniqueTrayMessage {
    param(
        [System.Collections.Generic.List[string]]$Target,
        [AllowNull()][string]$Message
    )

    if ([string]::IsNullOrWhiteSpace($Message)) { return }

    $normalized = Format-TrayUserFacingText -Text $Message
    if ([string]::IsNullOrWhiteSpace($normalized)) { return }
    if (-not $Target.Contains($normalized)) {
        [void]$Target.Add($normalized)
    }
}

function Get-ExitCodeDescriptor {
    param([AllowNull()][object]$ExitCode)

    if ($null -eq $ExitCode) {
        return "not reported"
    }

    return "$ExitCode"
}

function Format-TrayUserFacingText {
    <#
    .SYNOPSIS
    Converts backend handler/setting identifiers into short tray-safe labels.

    .DESCRIPTION
    CLI JSON intentionally carries stable internal identifiers such as
    GraphicsSettingsHandler.mpo_disabled. The tray is the user's frequent
    status surface, so it should present those as concise setting names instead
    of raw class paths.
    #>
    param([AllowNull()][string]$Text)

    if ([string]::IsNullOrWhiteSpace($Text)) { return $null }

    $friendly = $Text.Trim()
    $replacements = [ordered]@{
        "GraphicsSettingsHandler.mpo_disabled" = "Graphics settings (MPO)"
        "GraphicsSettingsHandler.disable_mpo" = "Graphics settings (MPO)"
        "WindowsSettingsHandler.windowed_optimizations" = "Windows windowed optimizations"
        "WindowsSettingsHandler.vrr_optimize" = "Windows VRR optimization"
        "WindowsSettingsHandler.hdr" = "Windows HDR"
        "WindowsSettingsHandler.refresh_rate" = "Windows refresh rate"
        "WindowsSettingsHandler.max_refresh_rate" = "Windows refresh rate"
        "NvidiaSettingsHandler.monitor_adaptive_sync" = "Monitor Adaptive Sync"
        "NvidiaSettingsHandler.app_binding" = "NVIDIA app binding"
        "NvidiaSettingsHandler.frame_rate_cap" = "NVIDIA frame-rate cap"
        "OW2ConfigHandler.frame_rate_cap" = "Overwatch 2 frame-rate cap"
        "OW2ConfigHandler.window_mode" = "Overwatch 2 display mode"
        "GraphicsSettingsHandler" = "Graphics settings"
        "WindowsSettingsHandler" = "Windows display settings"
        "NvidiaSettingsHandler" = "NVIDIA settings"
        "OW2ConfigHandler" = "Overwatch 2 config"
        "ColorProfileSettingsHandler" = "Color profile"
        "DisplayColorRangeHandler" = "Display color range"
        "RegistrySettingsHandler" = "Windows registry settings"
        "PowerSettingsHandler" = "Power plan"
        "NetworkSettingsHandler" = "Network settings"
        "MouseSettingsHandler" = "Mouse settings"
        "MemorySettingsHandler" = "Memory settings"
        "ProcessPriorityHandler" = "Process priority"
    }

    foreach ($key in $replacements.Keys) {
        $friendly = $friendly -replace [regex]::Escape($key), $replacements[$key]
    }

    return (Format-TrayDisplayCopy -Text $friendly)
}

function Format-TrayDisplayCopy {
    param([AllowNull()][string]$Text)

    if ([string]::IsNullOrWhiteSpace($Text)) { return $null }

    $display = "$Text".Trim()
    $display = [regex]::Replace(
        $display,
        '(?i)\bG[\s_-]?SYNC\b',
        'G-SYNC'
    )
    return $display
}

function Get-ApplyWarningMessages {
    param($Json)

    $messages = [System.Collections.Generic.List[string]]::new()

    if ($Json.data -and $Json.data.warnings) {
        foreach ($warning in @($Json.data.warnings)) {
            Add-UniqueTrayMessage -Target $messages -Message (Convert-ApplyWarningTextToPlainEnglish -Message "$warning")
        }
    }

    if ($Json.data -and $Json.data.transaction -and $Json.data.transaction.checkpoints) {
        foreach ($checkpoint in @($Json.data.transaction.checkpoints)) {
            if ("$($checkpoint.status)".ToLowerInvariant() -eq "warn") {
                Add-UniqueTrayMessage -Target $messages -Message (Convert-ApplyWarningTextToPlainEnglish -Message "$($checkpoint.message)")
            }
        }
    }

    if ($Json.data -and $Json.data.compliance -and $Json.data.compliance.issues) {
        foreach ($issue in @($Json.data.compliance.issues)) {
            if ("$($issue.severity)".ToLowerInvariant() -ne "warning") { continue }

            $detail = if ($issue.details) {
                "$($issue.message): $($issue.details)"
            }
            else {
                "$($issue.message)"
            }
            Add-UniqueTrayMessage -Target $messages -Message (Convert-ApplyWarningTextToPlainEnglish -Message $detail)
        }
    }

    return @($messages)
}

function Convert-ApplyWarningTextToPlainEnglish {
    param([AllowNull()][string]$Message)

    $friendly = Format-TrayUserFacingText -Text $Message
    if ([string]::IsNullOrWhiteSpace($friendly)) { return $null }

    if ($friendly -match "NVIDIA profile binding needs one manual step:\s*(?<action>Add .+)") {
        return "Manual NVIDIA step: $($Matches.action)"
    }

    if ($friendly -match "NVIDIA app binding requires manual action:\s*ABSO could not prove that (?<exe>.+?) already belong to NVIDIA profile '(?<profile>[^']+)'") {
        $exe = $Matches.exe.Trim()
        $profile = $Matches.profile.Trim()
        return "Manual NVIDIA step: Add $exe to NVIDIA profile '$profile' in NVIDIA Control Panel, then apply again."
    }

    if ($friendly -match "ABSO could not prove that (?<exe>.+?) already belong to NVIDIA profile '(?<profile>[^']+)'") {
        $exe = $Matches.exe.Trim()
        $profile = $Matches.profile.Trim()
        return "Manual NVIDIA step: Add $exe to NVIDIA profile '$profile' in NVIDIA Control Panel, then apply again."
    }

    if ($friendly -match "^(Compliance warnings detected|Verification reported mismatches)$") {
        return $null
    }

    return $friendly
}

function Get-ApplyNoticeMessages {
    param($Json)

    $messages = [System.Collections.Generic.List[string]]::new()

    if ($Json.data -and $Json.data.notices) {
        foreach ($notice in @($Json.data.notices)) {
            Add-UniqueTrayMessage -Target $messages -Message (Convert-ApplyNoticeTextToPlainEnglish -Message "$notice")
        }
    }

    return @($messages)
}

function Convert-ApplyNoticeTextToPlainEnglish {
    param([AllowNull()][string]$Message)

    $friendly = Format-TrayUserFacingText -Text $Message
    if ([string]::IsNullOrWhiteSpace($friendly)) { return $null }

    if ($friendly -match "NVIDIA predefined profile '(?<profile>[^']+)' already exists") {
        return "NVIDIA profile '$($Matches.profile)' was updated; exact app ownership could not be read."
    }

    if ($friendly -match "Proceeding with stable NVIDIA profile reuse:.*Profile '(?<profile>[^']+)'") {
        return "NVIDIA profile '$($Matches.profile)' was reused; exact app ownership could not be read."
    }

    if ($friendly -match "Profile '(?<profile>[^']+)' already exists and has bound applications") {
        return "NVIDIA profile '$($Matches.profile)' was updated; exact app ownership could not be read."
    }

    return $friendly
}

function Convert-ApplyFailureTextToPlainEnglish {
    param(
        [AllowNull()][string]$Message,
        [AllowNull()]$Json
    )

    $raw = if ([string]::IsNullOrWhiteSpace($Message)) { "" } else { "$Message".Trim() }
    $friendly = Format-TrayUserFacingText -Text $raw
    if ([string]::IsNullOrWhiteSpace($friendly)) { $friendly = $raw }

    $searchText = $friendly
    if ($Json.data -and $Json.data.compliance -and $Json.data.compliance.issues) {
        foreach ($issue in @($Json.data.compliance.issues)) {
            if ($issue.details) { $searchText += " $($issue.details)" }
            if ($issue.message) { $searchText += " $($issue.message)" }
        }
    }

    $restoredPrefix = ""
    if ($Json.data -and $Json.data.transaction -and $Json.data.transaction.rollback_performed) {
        $restoredPrefix = " Previous settings were restored."
    }

    if ($searchText -match "ABSO could not prove that (?<exe>.+?) already belong to NVIDIA profile '(?<profile>[^']+)'") {
        $exe = $Matches.exe.Trim()
        $profile = $Matches.profile.Trim()
        return "Not applied.$restoredPrefix Add $exe to NVIDIA profile '$profile' in NVIDIA Control Panel, then apply again."
    }

    if ($searchText -match "Executable binding could not be proven for:\s*(?<exe>[^.;]+)") {
        $exe = $Matches.exe.Trim()
        return "Not applied.$restoredPrefix NVIDIA could not confirm the game is attached to the right driver profile. Add $exe in NVIDIA Control Panel, then apply again."
    }

    if ($friendly -match "Mixed-refresh display path blocks strict VRR") {
        return "Not applied. This strict G-SYNC path is blocked by the current display setup. Use the safe fallback profile or fix the display path, then apply again."
    }

    if ($friendly -match "NVIDIA backup unavailable: Nvidia Profile Inspector was not found") {
        return "Not applied. NVIDIA Profile Inspector is missing, so ABSO could not safely back up driver settings. Restore NPI, then apply again."
    }

    if ($friendly -match "Critical compliance failure; restored backup automatically") {
        return "Not applied. Previous settings were restored because verification found a blocking mismatch. Open the tray log for the exact handler."
    }

    if ($friendly -match "Backend reported failure without a detailed error message") {
        return "Not applied. The backend did not return a detailed reason. Open the tray log for the raw command output."
    }

    if ($friendly -match "^(Not applied\.|Profile missing|Apply timed out)") {
        return $friendly
    }

    return "Not applied. $friendly"
}

function Get-ApplyPostApplyNoteMessages {
    param($Json)

    $messages = [System.Collections.Generic.List[string]]::new()

    if ($Json.data -and $Json.data.post_apply_notes) {
        foreach ($note in @($Json.data.post_apply_notes)) {
            Add-UniqueTrayMessage -Target $messages -Message "$note"
        }
    }

    return @($messages)
}

function Add-NvidiaManualBindingToastActionsFromText {
    param(
        [System.Collections.Generic.List[object]]$Target,
        [AllowNull()][string]$Text
    )

    if (-not $Target) { return }
    if ($Target.Count -ge 2) { return }
    if ([string]::IsNullOrWhiteSpace($Text)) { return }

    $message = "$Text"
    if ($message -match "Add (?<exe>.+?) to NVIDIA profile '(?<profile>[^']+)") {
        $exe = $Matches.exe.Trim()
        $profile = $Matches.profile.Trim()
        Add-TrayToastActionButton -Target $Target -Button (New-TrayToastActionButton `
            -Kind "open_nvidia_profile_inspector" `
            -Label "Open NPI" `
            -ProfileName $profile `
            -Executable $exe)
        if ($Target.Count -lt 2 -and -not [string]::IsNullOrWhiteSpace($exe)) {
            Add-TrayToastActionButton -Target $Target -Button (New-TrayToastActionButton `
                -Kind "copy_text" `
                -Label "Copy EXE" `
                -Text $exe `
                -ProfileName $profile `
                -Executable $exe)
        }
        return
    }

    if ($message -match "Add (?<exe>[^.;]+?) in NVIDIA Control Panel") {
        $exe = $Matches.exe.Trim()
        Add-TrayToastActionButton -Target $Target -Button (New-TrayToastActionButton `
            -Kind "open_nvidia_control_panel" `
            -Label "Open NVIDIA" `
            -Executable $exe)
        if ($Target.Count -lt 2 -and -not [string]::IsNullOrWhiteSpace($exe)) {
            Add-TrayToastActionButton -Target $Target -Button (New-TrayToastActionButton `
                -Kind "copy_text" `
                -Label "Copy EXE" `
                -Text $exe `
                -Executable $exe)
        }
    }
}

function Get-ApplyManualActionButtons {
    param($Json)

    $buttons = [System.Collections.Generic.List[object]]::new()

    if ($Json.data -and $Json.data.manual_actions) {
        foreach ($action in @($Json.data.manual_actions)) {
            $kind = Get-TrayToastActionValue -Action $action -Names @("type", "Type", "kind", "Kind")
            $label = Get-TrayToastActionValue -Action $action -Names @("label", "Label")
            $profileName = Get-TrayToastActionValue -Action $action -Names @("profile_name", "ProfileName")
            $executable = Get-TrayToastActionValue -Action $action -Names @("executable", "Executable")
            $text = Get-TrayToastActionValue -Action $action -Names @("text", "Text")
            $uri = Get-TrayToastActionValue -Action $action -Names @("uri", "Uri")
            Add-TrayToastActionButton -Target $buttons -Button (New-TrayToastActionButton `
                -Kind "$kind" `
                -Label "$label" `
                -ProfileName "$profileName" `
                -Executable "$executable" `
                -Text "$text" `
                -Uri "$uri")
            if ($buttons.Count -ge 2) { break }
        }
    }

    if ($buttons.Count -lt 2) {
        foreach ($warning in @(Get-ApplyWarningMessages -Json $Json)) {
            Add-NvidiaManualBindingToastActionsFromText -Target $buttons -Text "$warning"
            if ($buttons.Count -ge 2) { break }
        }
    }

    return @($buttons)
}

function Get-ApplyFailureActionButtons {
    param(
        [AllowNull()][string]$Message,
        [AllowNull()]$Json
    )

    $buttons = [System.Collections.Generic.List[object]]::new()
    Add-NvidiaManualBindingToastActionsFromText -Target $buttons -Text $Message

    if ($buttons.Count -lt 2 -and $Json) {
        foreach ($warning in @(Get-ApplyWarningMessages -Json $Json)) {
            Add-NvidiaManualBindingToastActionsFromText -Target $buttons -Text "$warning"
            if ($buttons.Count -ge 2) { break }
        }
    }

    return @($buttons)
}

function Get-WarningSummaryText {
    param(
        [string[]]$Warnings,
        [string]$Label = "Warning"
    )

    if (-not $Warnings -or $Warnings.Count -eq 0) { return $null }
    if ($Warnings.Count -eq 1) { return "${Label}: $($Warnings[0])" }

    $pluralLabel = if ($Label.EndsWith("s")) { $Label } else { "${Label}s" }
    return "${pluralLabel}: $($Warnings[0]) (+$($Warnings.Count - 1) more)"
}

function Get-NoticeSummaryText {
    param([string[]]$Notices)

    if (-not $Notices -or $Notices.Count -eq 0) { return $null }
    if ($Notices.Count -eq 1) { return "Note: $($Notices[0])" }
    return "Notes: $($Notices[0]) (+$($Notices.Count - 1) more)"
}

function Get-ApplySummaryLevel {
    param($Json)

    $summaryLevel = if ($Json.data -and $Json.data.summary_level) {
        "$($Json.data.summary_level)".ToLowerInvariant()
    }
    else {
        ""
    }

    switch ($summaryLevel) {
        "success" { return "success" }
        "notice" { return "notice" }
        "caution" { return "caution" }
        "warning" { return "warning" }
        default { return "success" }
    }
}

function Get-ApplyFailureMessage {
    param(
        $Json,
        [string[]]$FailedHandlers,
        [AllowNull()][object]$ExitCode
    )

    if ($FailedHandlers.Count -gt 0) {
        $friendlyHandlers = @($FailedHandlers | ForEach-Object { Format-TrayUserFacingText -Text "$_" })
        return (Convert-ApplyFailureTextToPlainEnglish `
            -Message "Failed settings: $($friendlyHandlers -join ', ')" `
            -Json $Json)
    }
    elseif ($Json.error) {
        return (Convert-ApplyFailureTextToPlainEnglish -Message "$($Json.error)" -Json $Json)
    }
    elseif ($Json.data -and $Json.data.error) {
        return (Convert-ApplyFailureTextToPlainEnglish -Message "$($Json.data.error)" -Json $Json)
    }
    elseif ($Json.data -and $Json.data.failed_settings -and $Json.data.failed_settings.Count -gt 0) {
        return (Convert-ApplyFailureTextToPlainEnglish `
            -Message ($Json.data.failed_settings -join "; ") `
            -Json $Json)
    }

    return (Convert-ApplyFailureTextToPlainEnglish `
        -Message "Backend reported failure without a detailed error message (exit code: $(Get-ExitCodeDescriptor -ExitCode $ExitCode))" `
        -Json $Json)
}

function Get-TrayProfileGameGroup {
    param(
        [string]$ProfileId,
        [object]$Profile
    )

    if ($Profile -and -not [string]::IsNullOrWhiteSpace("$($Profile.GameGroup)")) {
        return "$($Profile.GameGroup)"
    }

    $variantSuffixes = @(
        "-online-gsync-hdr-capture", "-online-gsync-hdr",
        "-gsync-hdr-capture", "-gsync-capture",
        "-online-gsync", "-offline-gsync-hdr",
        "-offline-hdr", "-online-hdr", "-console-parity-hdr",
        "-universal-hdr", "-gsync-hdr", "-tournament-sim-144hz",
        "-console-parity", "-300hz-max", "-streaming-hdr", "-streaming",
        "-offline", "-online", "-vrr-lab", "-gsync", "-hdr", "-sdr",
        "-universal", "-capture"
    )
    foreach ($suffix in $variantSuffixes) {
        if ($ProfileId.EndsWith($suffix)) {
            return $ProfileId.Substring(0, $ProfileId.Length - $suffix.Length)
        }
    }
    return $ProfileId
}

function Get-TrayProfileToastVisualArgs {
    param(
        [string]$ProfileId,
        [object]$Profile,
        [switch]$ActiveBadge
    )

    if ([string]::IsNullOrWhiteSpace($ProfileId)) { return @{} }
    if (-not $Profile -and $script:Profiles -and $script:Profiles.Contains($ProfileId)) {
        $Profile = $script:Profiles[$ProfileId]
    }

    # Catalog-drift or user-profile misses still get deterministic stylized
    # profile-id art instead of collapsing to a generic brand-only toast.
    $category = if ($Profile -and $Profile.Cat) { "$($Profile.Cat)" } else { "Other" }
    $gameGroup = Get-TrayProfileGameGroup -ProfileId $ProfileId -Profile $Profile
    $color = Get-TrayProfileAccentColor -ProfileId $ProfileId -Profile $Profile -Fallback $script:Colors.Text
    $variant = if ($Profile -and $Profile.Variant) { "$($Profile.Variant)" } else { "" }
    $modeBadge = if ("$ProfileId" -match '(?i)capture' -or $variant -match '(?i)capture') {
        "capture"
    }
    elseif ($variant -match '(?i)\bHDR\b' -or "$ProfileId" -match '(?i)-hdr($|-)' ) {
        "hdr"
    }
    else {
        ""
    }
    $favoriteBadge = if (Get-Command Test-Favorite -ErrorAction SilentlyContinue) {
        Test-Favorite -ProfileId $ProfileId -Config $script:TrayConfig
    }
    else {
        $false
    }

    return @{
        ProfileGameGroup = $gameGroup
        ProfileCategory = $category
        ProfileColor = $color
        ProfileActiveBadge = [bool]$ActiveBadge
        ProfileModeBadge = $modeBadge
        ProfileFavoriteBadge = [bool]$favoriteBadge
    }
}

function Get-SyncTransitionDirection {
    # Returns one of: "to_no_sync", "to_sync", "" — describing how the user is moving
    # between profile sync modes. Used to decide whether to nudge the user about
    # firmware Adaptive Sync state, and which direction.
    param(
        [string]$FromProfileId,
        [string]$ToProfileId
    )

    if ([string]::IsNullOrWhiteSpace($FromProfileId) -or [string]::IsNullOrWhiteSpace($ToProfileId)) {
        return ""
    }

    $fromProfile = $script:Profiles[$FromProfileId]
    $toProfile = $script:Profiles[$ToProfileId]
    if (-not $fromProfile -or -not $toProfile) { return "" }

    $fromSyncMode = if ($fromProfile.SyncMode) { "$($fromProfile.SyncMode)".ToLowerInvariant() } else { "" }
    $toSyncMode = if ($toProfile.SyncMode) { "$($toProfile.SyncMode)".ToLowerInvariant() } else { "" }
    if (($fromSyncMode -eq "on") -and ($toSyncMode -eq "off")) {
        return "to_no_sync"
    }
    if (($fromSyncMode -eq "off") -and ($toSyncMode -eq "on")) {
        return "to_sync"
    }

    $fromText = (($fromProfile.Name, $fromProfile.Sub, $fromProfile.Desc) -join " ").ToLowerInvariant()
    $toText = (($toProfile.Name, $toProfile.Sub, $toProfile.Desc) -join " ").ToLowerInvariant()

    # Fall back to profile metadata text when SyncMode is unset/agnostic.
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
    if ($fromSyncOn -and $toSyncOff) { return "to_no_sync" }

    $fromSyncOff = (
        $fromText -match "\bg-?sync\s*off\b" -or
        $fromText -match "\bvrr\s*off\b" -or
        $fromText -match "\bno[-\s]?sync\b" -or
        $fromText -match "\bno\s+vrr\b"
    )
    $toSyncOn = (
        $toText -match "\bg-?sync\s*on\b" -or
        $toText -match "\bvrr\s*on\b"
    )
    if ($fromSyncOff -and $toSyncOn) { return "to_sync" }

    return ""
}

function Test-NeedsNoSyncOsdReminder {
    # Backwards-compatible wrapper — kept so any external/tray callers still resolve.
    param(
        [string]$FromProfileId,
        [string]$ToProfileId
    )
    return ((Get-SyncTransitionDirection -FromProfileId $FromProfileId -ToProfileId $ToProfileId) -eq "to_no_sync")
}

$script:SoundFilesChecked = $false

function Test-SoundFilesExist {
    # Only log warnings once per session
    if ($script:SoundFilesChecked) { return ($script:SoundFilesValid) }
    $script:SoundFilesChecked = $true
    $script:SoundFilesValid = $true

    foreach ($soundEvent in @("success", "fail", "vrrWarning", "restart")) {
        $cue = Get-ThemeSoundCue -SoundEvent $soundEvent
        if ($cue.Type -eq "file" -and -not (Test-Path $cue.Path)) {
            Write-TrayLog "THEME SOUND FILE MISSING ($soundEvent): $($cue.Path)" -Level "WARN"
            $script:SoundFilesValid = $false
        }
    }
    if ($script:SoundFilesValid) { Write-TrayLog "Theme sound cues validated" }
    return $script:SoundFilesValid
}

# ============================================================================
# DARK THEME COLORS
# ============================================================================

# Shared Penumbra palette. Key names are kept stable for existing callsites,
# but all values come from ABSO-Theme.ps1 so every tray surface stays aligned.
if (Get-Command Get-TrayThemePalette -ErrorAction SilentlyContinue) {
    $script:Colors = Get-TrayThemePalette
}
else {
    $script:Colors = @{
        Background      = [System.Drawing.Color]::FromArgb(255, 7, 24, 29)
        BackgroundDark  = [System.Drawing.Color]::FromArgb(255, 4, 15, 18)
        BackgroundLight = [System.Drawing.Color]::FromArgb(255, 16, 52, 60)
        Hover           = [System.Drawing.Color]::FromArgb(255, 20, 66, 74)
        HoverBright     = [System.Drawing.Color]::FromArgb(255, 25, 82, 90)
        Text            = [System.Drawing.Color]::FromArgb(255, 225, 244, 240)
        TextDim         = [System.Drawing.Color]::FromArgb(255, 148, 183, 182)
        TextDisabled    = [System.Drawing.Color]::FromArgb(255, 95, 127, 127)
        Border          = [System.Drawing.Color]::FromArgb(255, 26, 88, 90)
        Separator       = [System.Drawing.Color]::FromArgb(255, 12, 44, 49)
        AccentGold      = [System.Drawing.Color]::FromArgb(255, 0, 245, 212)
        AccentGreen     = [System.Drawing.Color]::FromArgb(255, 61, 222, 147)
        AccentBlue      = [System.Drawing.Color]::FromArgb(255, 82, 199, 244)
        AccentPurple    = [System.Drawing.Color]::FromArgb(255, 183, 156, 255)
        AccentAmber     = [System.Drawing.Color]::FromArgb(255, 245, 184, 64)
        AccentRed       = [System.Drawing.Color]::FromArgb(255, 255, 92, 120)
        AccentTeal      = [System.Drawing.Color]::FromArgb(255, 64, 201, 181)
        FavoriteStar    = [System.Drawing.Color]::FromArgb(255, 245, 184, 64)
        CategoryDesktop = [System.Drawing.Color]::FromArgb(255, 0, 245, 212)
        CategoryFighting = [System.Drawing.Color]::FromArgb(255, 255, 110, 122)
        CategoryShooter = [System.Drawing.Color]::FromArgb(255, 82, 199, 244)
        CategoryRpg     = [System.Drawing.Color]::FromArgb(255, 183, 156, 255)
        CategoryOther   = [System.Drawing.Color]::FromArgb(255, 61, 222, 147)
        CatFighting     = [System.Drawing.Color]::FromArgb(255, 255, 110, 122)
        CatARPG         = [System.Drawing.Color]::FromArgb(255, 183, 156, 255)
        CatShooter      = [System.Drawing.Color]::FromArgb(255, 82, 199, 244)
        CatStreaming    = [System.Drawing.Color]::FromArgb(255, 64, 201, 181)
        CatOther        = [System.Drawing.Color]::FromArgb(255, 61, 222, 147)
        CatProd         = [System.Drawing.Color]::FromArgb(255, 245, 184, 64)
    }
}

# ============================================================================
# LOGGING
# ============================================================================

$script:LogFile = Join-Path $env:TEMP "abso_tray.log"
$script:LogMaxBytes = 2 * 1024 * 1024  # 2 MB max log size
$script:LogCheckedSize = $false

$script:LogUtf8NoBom = [System.Text.UTF8Encoding]::new($false)

function Write-TrayLog {
    param([string]$Message, [string]$Level = "INFO")
    # [DateTime]::Now.ToString(...) is ~3x faster than Get-Date -Format
    # because it skips PowerShell's pipeline + cmdlet binding.
    $line = "[$([DateTime]::Now.ToString('yyyy-MM-dd HH:mm:ss'))] [$Level] $Message`r`n"
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
        # [System.IO.File]::AppendAllText is ~2-3x faster than Add-Content
        # because it bypasses PowerShell's pipeline + provider plumbing.
        [System.IO.File]::AppendAllText($script:LogFile, $line, $script:LogUtf8NoBom)
    }
    catch {}
}

function Invoke-JsonSafe {
    <#
    .SYNOPSIS
    Parse JSON text without crashing the tray on malformed input.

    .DESCRIPTION
    The Python CLI normally emits clean JSON, but any stderr leak, partial
    write, or encoding hiccup used to propagate as an unhandled
    ConvertFrom-Json exception and take the tray with it. This helper
    returns $null on parse failure and logs a bounded preview of the
    offending text so the failure is diagnosable from the tray log.

    .PARAMETER Text
    Raw string to parse.

    .PARAMETER Source
    Short label (e.g. 'ApplyProfile', 'Audit', 'Restore') recorded in the
    log so the operator can tell which call site produced the malformed
    payload.
    #>
    param(
        [string]$Text,
        [string]$Source = "unknown"
    )
    if ([string]::IsNullOrWhiteSpace($Text)) {
        Write-TrayLog "Invoke-JsonSafe[$Source]: empty or whitespace input" -Level "WARN"
        return $null
    }
    try {
        return ($Text | ConvertFrom-Json -ErrorAction Stop)
    }
    catch {
        $preview = $Text.Trim()
        if ($preview.Length -gt 400) {
            $preview = $preview.Substring(0, 400) + "...<truncated>"
        }
        Write-TrayLog "Invoke-JsonSafe[$Source]: parse failed: $($_.Exception.Message) | first 400 chars: $preview" -Level "ERROR"
        return $null
    }
}

function Reset-ActiveProfileVerificationState {
    $script:ActiveProfileVerificationStatus = $null
    $script:ActiveProfilePendingApplySettings = @()
    $script:ActiveProfilePendingRebootSettings = @()
    $script:ActiveProfileMismatchedHandlers = @()
    $script:ActiveProfileVerificationCheckedAt = $null
    $script:ActiveProfileStateRebootPending = $false
    $script:ActiveProfileStateRebootReasons = @()
}

# Startup verification is deferred (see the deferral note near the end of
# Initialize), so nothing seeds these until the first apply or verify runs.
# Uninitialized ($null) lists wrapped in @() have Count 1, which made
# Get-ActiveProfileRebootPendingText fall through to its "profile changes"
# fallback and render a phantom "Windows restart required" banner on every
# cold start. Initialize the state explicitly so renderers see empty, not
# $null.
Reset-ActiveProfileVerificationState

function Set-ActiveProfileVerificationSeedFromApplyData {
    <#
    .SYNOPSIS
    Seeds tray status from the apply/apply-pending result before the slower
    verifier refresh completes.
    #>
    param([AllowNull()][object]$Data)

    Reset-ActiveProfileVerificationState
    if ($null -eq $Data) { return }

    $pendingApplyAfter = @()
    if ($Data.PSObject.Properties["pending_apply_settings_after"]) {
        $pendingApplyAfter = @($Data.pending_apply_settings_after)
    }
    $pendingApplyAfter = @($pendingApplyAfter | Where-Object { -not [string]::IsNullOrWhiteSpace("$($_)") })

    $pendingRebootAfter = @()
    if ($Data.PSObject.Properties["pending_reboot_gated_settings_after"]) {
        $pendingRebootAfter = @($Data.pending_reboot_gated_settings_after)
    }
    $pendingRebootAfter = @($pendingRebootAfter | Where-Object { -not [string]::IsNullOrWhiteSpace("$($_)") })

    $requiresReboot = $false
    if ($Data.PSObject.Properties["requires_reboot"]) {
        $requiresReboot = [bool]$Data.requires_reboot
    }
    elseif ($Data.PSObject.Properties["reboot_pending"]) {
        $requiresReboot = [bool]$Data.reboot_pending
    }

    $rebootReasons = @()
    if ($Data.PSObject.Properties["reboot_reasons"]) {
        $rebootReasons = @($Data.reboot_reasons)
    }
    $rebootReasons = @($rebootReasons | Where-Object { -not [string]::IsNullOrWhiteSpace("$($_)") })

    if ($pendingApplyAfter.Count -gt 0) {
        $script:ActiveProfileVerificationStatus = "pending_apply"
        $script:ActiveProfilePendingApplySettings = $pendingApplyAfter
        $script:ActiveProfilePendingRebootSettings = $pendingRebootAfter
        $script:ActiveProfileStateRebootPending = $requiresReboot
        $script:ActiveProfileStateRebootReasons = $rebootReasons
    }
    elseif ($requiresReboot -or $pendingRebootAfter.Count -gt 0) {
        $script:ActiveProfileVerificationStatus = "pending_reboot"
        $script:ActiveProfilePendingRebootSettings = $pendingRebootAfter
        $script:ActiveProfileStateRebootPending = $true
        if ($rebootReasons.Count -gt 0) {
            $script:ActiveProfileStateRebootReasons = $rebootReasons
        }
        elseif ($pendingRebootAfter.Count -gt 0) {
            $script:ActiveProfileStateRebootReasons = $pendingRebootAfter
        }
        else {
            $script:ActiveProfileStateRebootReasons = @("profile changes")
        }
    }
    else {
        $script:ActiveProfileVerificationStatus = "active"
    }

    $script:ActiveProfileVerificationCheckedAt = (Get-Date).ToString("o")
}

function Test-ActiveProfileVerificationInFlight {
    if (-not $script:ActiveProfileVerifyProc) { return $false }
    try {
        return (-not $script:ActiveProfileVerifyProc.HasExited)
    }
    catch {
        return $false
    }
}

function Get-ActiveProfilePendingApplyText {
    if ($script:ActiveProfileVerificationStatus -notin @("pending_apply", "mismatch")) { return $null }
    $pending = @($script:ActiveProfilePendingApplySettings)
    if ($pending.Count -gt 0 -and -not [string]::IsNullOrWhiteSpace("$($pending[0])")) {
        return (Format-TrayUserFacingText -Text "$($pending[0])")
    }
    if ($script:ActiveProfileVerificationStatus -eq "mismatch") {
        $mismatches = @($script:ActiveProfileMismatchedHandlers) |
            Where-Object { -not [string]::IsNullOrWhiteSpace("$($_)") } |
            Select-Object -First 2
        if ($mismatches.Count -gt 0) {
            return (Format-TrayUserFacingText -Text ($mismatches -join ", "))
        }
        return "profile mismatch"
    }
    return "profile verification"
}

function Get-ActiveProfileRebootPendingText {
    # Filter blanks so an unseeded $null list reads as empty; @($null) has
    # Count 1 and previously defeated both early-return guards below.
    $pending = @(
        @($script:ActiveProfilePendingRebootSettings) |
            Where-Object { -not [string]::IsNullOrWhiteSpace("$($_)") }
    )
    if (
        $script:ActiveProfileVerificationStatus -eq "active" -and
        $pending.Count -eq 0
    ) {
        return $null
    }

    if (
        -not $script:ActiveProfileStateRebootPending -and
        $script:ActiveProfileVerificationStatus -ne "pending_reboot" -and
        $pending.Count -eq 0
    ) {
        return $null
    }
    $reasons = @(
        @($script:ActiveProfileStateRebootReasons) |
            Where-Object { -not [string]::IsNullOrWhiteSpace("$($_)") }
    )
    if ($reasons.Count -gt 0 -and -not [string]::IsNullOrWhiteSpace("$($reasons[0])")) {
        return (Format-TrayUserFacingText -Text "$($reasons[0])")
    }
    if ($pending.Count -gt 0 -and -not [string]::IsNullOrWhiteSpace("$($pending[0])")) {
        return (Format-TrayUserFacingText -Text "$($pending[0])")
    }
    return "profile changes"
}

function Get-ActiveProfileVerificationInProgressText {
    if ([string]::IsNullOrWhiteSpace([string]$script:activeProfile)) { return $null }
    if (-not (Test-ActiveProfileVerificationInFlight)) { return $null }
    if (Get-ActiveProfilePendingApplyText) { return $null }
    if (Get-ActiveProfileRebootPendingText) { return $null }
    return "checking profile state"
}

function Complete-SameActiveProfileSelectionIfHandled {
    <#
    .SYNOPSIS
    Handles tray clicks on the already-active profile without redundant apply.

    .DESCRIPTION
    The active profile may already be fully verified or waiting only for a
    reboot-gated compositor change. Re-running a full apply for that state can
    rewrite display-sensitive settings and blank a secondary monitor. This
    function turns those clicks into a no-op status notice, and routes the one
    supported repair state through the narrow apply-pending path.
    #>
    param(
        [string]$ProfileId,
        [object]$Profile
    )

    $pendingApplyText = Get-ActiveProfilePendingApplyText
    if (
        -not [string]::IsNullOrWhiteSpace($pendingApplyText) -and
        $script:ActiveProfileVerificationStatus -ne "mismatch"
    ) {
        Write-TrayLog "Profile '$ProfileId' is already active but needs pending fixes; using apply-pending instead of full apply"
        Apply-PendingProfileFixes
        return $true
    }

    $status = if ($script:ActiveProfileVerificationStatus) { "$($script:ActiveProfileVerificationStatus)" } else { "" }
    $rebootText = Get-ActiveProfileRebootPendingText
    $alreadyVerified = $status -in @("active", "pending_reboot")
    $sameActiveNoticeVisual = Get-TrayProfileToastVisualArgs -ProfileId $ProfileId -Profile $Profile
    $profileTitle = Get-TrayProfileObjectDisplayName -Profile $Profile -Fallback $ProfileId

    if ($alreadyVerified -or -not [string]::IsNullOrWhiteSpace($rebootText)) {
        Set-IconState -State "Active"
        if (-not [string]::IsNullOrWhiteSpace($rebootText)) {
            Write-TrayLog "Profile '$ProfileId' already verifies active; skipping apply. Windows restart required: $rebootText"
            Show-Notification @sameActiveNoticeVisual -Title $profileTitle -Message "Already active. Windows restart required: $rebootText" -Type "Warning" -MetaText $ProfileId
            $script:LastAction = "Windows restart required: $rebootText"
        }
        else {
            Write-TrayLog "Profile '$ProfileId' already verifies active; skipping redundant apply"
            Show-Notification @sameActiveNoticeVisual -Title $profileTitle -Message "Already active." -Type "Info" -MetaText $ProfileId
            $script:LastAction = "Already active: $profileTitle"
        }
        $script:LastActionTime = Get-Date
        Update-MenuState
        Start-ActiveProfileVerificationTimer -DelayMilliseconds 500
        return $true
    }

    if ([string]::IsNullOrWhiteSpace($status)) {
        Write-TrayLog "Profile '$ProfileId' is already active but verification has not completed; refreshing before any apply"
        Show-Notification @sameActiveNoticeVisual -Title $profileTitle -Message "Verifying current profile before reapply." -Type "Info" -MetaText $ProfileId
        $script:LastAction = "Verifying: $profileTitle"
        $script:LastActionTime = Get-Date
        Refresh-ActiveProfileVerificationState -Silent
        return $true
    }

    return $false
}

function Refresh-ActiveProfileVerificationState {
    <#
    .SYNOPSIS
    Refreshes the tray's read-only view of whether the remembered profile is actually active.

    .DESCRIPTION
    Calls `abso state --json --verify`, which performs verifier readback only.
    This must not apply profiles, reset the display, or touch registry state.
    #>
    param([switch]$Silent)

    if ([string]::IsNullOrWhiteSpace([string]$script:activeProfile)) {
        Reset-ActiveProfileVerificationState
        Update-MenuState
        return
    }

    if (Test-ActiveProfileVerificationInFlight) {
        if (-not $Silent) { $script:ActiveProfileVerifySilent = $false }
        Write-TrayLog "State verification already running; coalescing refresh request"
        return
    }

    Reset-ActiveProfileVerificationState
    Start-ActiveProfileVerificationProcess -Silent:$Silent
}

function Set-ActiveProfileVerificationFailureAction {
    param([string]$Reason)

    $lastActionText = Normalize-TrayLastActionMessage -Message $script:LastAction
    if ([string]::IsNullOrWhiteSpace($lastActionText) -or -not $lastActionText.StartsWith("Verifying:")) { return }

    $failureReason = if ([string]::IsNullOrWhiteSpace($Reason)) { "reason not reported" } else { $Reason.Trim() }
    Set-TrayLastAction -Message "Verify failed: $failureReason"
}

function Set-ActiveProfileVerificationUnavailableAction {
    param([string]$Reason)

    $lastActionText = Normalize-TrayLastActionMessage -Message $script:LastAction
    $lastActionWasVerifierDerived = (
        -not [string]::IsNullOrWhiteSpace($lastActionText) -and (
        $lastActionText.StartsWith("Verifying:") -or
        $lastActionText.StartsWith("Pending profile fix:") -or
        $lastActionText.StartsWith("Profile mismatch:") -or
        $lastActionText.StartsWith("Windows restart required:")
        )
    )
    if (-not $lastActionWasVerifierDerived) { return }

    $cleanReason = if ([string]::IsNullOrWhiteSpace($Reason)) { "not current" } else { $Reason.Trim() }
    $statusPrefix = if ($cleanReason -in @("profile changed", "not current")) {
        "Verification not current"
    }
    else {
        "Verification status not reported"
    }
    Set-TrayLastAction -Message "${statusPrefix}: $cleanReason"
}

function Stop-ActiveProfileVerificationRuntime {
    param([switch]$KillProcess)

    if ($script:ActiveProfileVerifyTimer) {
        try { $script:ActiveProfileVerifyTimer.Stop(); $script:ActiveProfileVerifyTimer.Dispose() } catch {}
        $script:ActiveProfileVerifyTimer = $null
    }
    if ($script:ActiveProfileVerifyPollTimer) {
        try { $script:ActiveProfileVerifyPollTimer.Stop(); $script:ActiveProfileVerifyPollTimer.Dispose() } catch {}
        $script:ActiveProfileVerifyPollTimer = $null
    }
    if ($script:ActiveProfileVerifyProc) {
        try {
            if ($KillProcess -and -not $script:ActiveProfileVerifyProc.HasExited) {
                $script:ActiveProfileVerifyProc.Kill()
            }
        } catch {}
        try { $script:ActiveProfileVerifyProc.Dispose() } catch {}
        $script:ActiveProfileVerifyProc = $null
    }
    foreach ($path in @($script:ActiveProfileVerifyOutputFile, $script:ActiveProfileVerifyErrorFile)) {
        if ($path) { Remove-Item $path -Force -ErrorAction SilentlyContinue }
    }
    $script:ActiveProfileVerifyOutputFile = $null
    $script:ActiveProfileVerifyErrorFile = $null
    $script:ActiveProfileVerifyStartedAt = $null
    $script:ActiveProfileVerifySilent = $true
}

function Apply-ActiveProfileVerificationJson {
    param(
        [object]$Json,
        [switch]$Silent
    )

    if ($null -eq $Json -or -not $Json.success -or -not $Json.data) {
        throw "state --verify returned malformed or unsuccessful JSON"
    }

    $verification = $Json.data.verification
    if (-not $verification) {
        Write-TrayLog "State verification returned no verification block" -Level "WARN"
        Reset-ActiveProfileVerificationState
        Set-ActiveProfileVerificationUnavailableAction -Reason "missing verifier data"
        return
    }

    $verifiedProfile = if ($verification.profile) { "$($verification.profile)" } else { "" }
    if ($verifiedProfile -and $verifiedProfile -ne "$script:activeProfile") {
        Write-TrayLog "State verification profile '$verifiedProfile' does not match tray active profile '$script:activeProfile'" -Level "WARN"
        Reset-ActiveProfileVerificationState
        Set-ActiveProfileVerificationUnavailableAction -Reason "profile changed"
        return
    }

    $reportedStatus = if ($verification.status) { "$($verification.status)" } else { "" }
    if ([string]::IsNullOrWhiteSpace($reportedStatus)) {
        Write-TrayLog "State verification returned no verification status" -Level "WARN"
        Reset-ActiveProfileVerificationState
        Set-ActiveProfileVerificationUnavailableAction -Reason "missing verifier status"
        return
    }

    $script:ActiveProfileVerificationStatus = $reportedStatus
    $script:ActiveProfilePendingApplySettings = @($verification.pending_apply_settings)
    $script:ActiveProfilePendingRebootSettings = @($verification.pending_reboot_gated_settings)
    $script:ActiveProfileMismatchedHandlers = @($verification.mismatched_handlers)
    $script:ActiveProfileVerificationCheckedAt = if ($verification.checked_at) { "$($verification.checked_at)" } else { (Get-Date).ToString("o") }
    $script:ActiveProfileStateRebootPending = if ($Json.data.PSObject.Properties["reboot_pending"]) { [bool]$Json.data.reboot_pending } else { $false }
    $script:ActiveProfileStateRebootReasons = if ($Json.data.PSObject.Properties["reboot_reasons"]) { @($Json.data.reboot_reasons) } else { @() }

    if ($script:ActiveProfileVerificationStatus -eq "pending_apply") {
        $pendingText = Get-ActiveProfilePendingApplyText
        Write-TrayLog "Active profile has pending profile fixes: $pendingText" -Level "WARN"
        $script:LastAction = "Pending profile fix: $pendingText"
        $script:LastActionTime = Get-Date
    }
    elseif ($script:ActiveProfileVerificationStatus -eq "mismatch") {
        $pendingText = Get-ActiveProfilePendingApplyText
        Write-TrayLog "Active profile verification mismatch: $pendingText" -Level "WARN"
        $script:LastAction = "Profile mismatch: $pendingText"
        $script:LastActionTime = Get-Date
    }
    elseif ($script:ActiveProfileStateRebootPending) {
        $rebootText = Get-ActiveProfileRebootPendingText
        Write-TrayLog "Active profile has Windows restart-gated changes: $rebootText" -Level "WARN"
        $script:LastAction = "Windows restart required: $rebootText"
        $script:LastActionTime = Get-Date
    }
    elseif ($script:ActiveProfileVerificationStatus -eq "active") {
        $lastActionText = Normalize-TrayLastActionMessage -Message $script:LastAction
        $lastActionWasVerifierPending = (
            -not [string]::IsNullOrWhiteSpace($lastActionText) -and (
            $lastActionText.StartsWith("Pending profile fix:") -or
            $lastActionText.StartsWith("Profile mismatch:") -or
            $lastActionText.StartsWith("Windows restart required:")
            )
        )
        if ($lastActionWasVerifierPending) {
            $activeName = Get-TrayProfileDisplayName -ProfileId "$script:activeProfile"
            Write-TrayLog "Active profile now verifies clean; replacing stale verifier action '$lastActionText'"
            $script:LastAction = "Verified active: $activeName"
            $script:LastActionTime = Get-Date
        }
        elseif ([string]::IsNullOrWhiteSpace($lastActionText)) {
            # Fresh session with no action yet (e.g. the first verification
            # after an OS reboot): show a positive confirmation instead of an
            # empty status, so a user who just restarted Windows sees that the
            # restart-gated change committed instead of wondering whether the
            # pre-reboot "Windows restart required" notice still applies.
            $activeName = Get-TrayProfileDisplayName -ProfileId "$script:activeProfile"
            Write-TrayLog "Active profile verifies clean on fresh session; surfacing verified status"
            $script:LastAction = "Verified active: $activeName"
            $script:LastActionTime = Get-Date
        }
        elseif (-not $Silent) {
            Write-TrayLog "Active profile verification status: $script:ActiveProfileVerificationStatus"
        }
    }
    elseif (-not $Silent) {
        Write-TrayLog "Active profile verification status: $script:ActiveProfileVerificationStatus"
    }
}

function Start-ActiveProfileVerificationProcess {
    <#
    .SYNOPSIS
    Starts read-only active-profile verification without blocking the WinForms UI thread.
    #>
    param([switch]$Silent)

    if (Test-ActiveProfileVerificationInFlight) {
        if (-not $Silent) { $script:ActiveProfileVerifySilent = $false }
        Write-TrayLog "State verification already running; skipping duplicate process start"
        return
    }

    if ($script:ActiveProfileVerifyProc) {
        Complete-ActiveProfileVerificationIfReady
        if (Test-ActiveProfileVerificationInFlight) { return }
        Stop-ActiveProfileVerificationRuntime
    }

    if ([string]::IsNullOrWhiteSpace([string]$script:activeProfile)) {
        Update-MenuState
        return
    }

    try {
        $script:ActiveProfileVerifyOutputFile = [System.IO.Path]::GetTempFileName()
        $script:ActiveProfileVerifyErrorFile = "$($script:ActiveProfileVerifyOutputFile).err"
        $script:ActiveProfileVerifyStartedAt = [DateTime]::UtcNow
        $script:ActiveProfileVerifySilent = [bool]$Silent
        $stateArgs = Get-AbsoBackendArgs -CommandArgs @("state", "--json", "--verify")

        Write-TrayLog "Starting read-only state verification: $($script:PythonExe) $($stateArgs -join ' ')"
        $script:ActiveProfileVerifyProc = Start-Process -FilePath $script:PythonExe -ArgumentList $stateArgs `
            -NoNewWindow -PassThru -WorkingDirectory $script:ProjectRoot `
            -RedirectStandardOutput $script:ActiveProfileVerifyOutputFile `
            -RedirectStandardError $script:ActiveProfileVerifyErrorFile
        # PS 5.1: cache the handle now or .ExitCode reads $null after exit.
        if ($script:ActiveProfileVerifyProc) { $null = $script:ActiveProfileVerifyProc.Handle }

        $pollTimer = New-Object System.Windows.Forms.Timer
        $pollTimer.Interval = 250
        $pollTimer.Add_Tick({ Complete-ActiveProfileVerificationIfReady })
        $script:ActiveProfileVerifyPollTimer = $pollTimer
        $pollTimer.Start()
    }
    catch {
        Write-TrayLog "State verification start failed: $($_.Exception.Message)" -Level "WARN"
        Set-ActiveProfileVerificationFailureAction -Reason "$($_.Exception.Message)"
        Stop-ActiveProfileVerificationRuntime -KillProcess
        Update-MenuState
    }
}

function Complete-ActiveProfileVerificationIfReady {
    $proc = $script:ActiveProfileVerifyProc
    if (-not $proc) {
        Stop-ActiveProfileVerificationRuntime
        return
    }

    $elapsedSeconds = if ($script:ActiveProfileVerifyStartedAt) {
        ([DateTime]::UtcNow - $script:ActiveProfileVerifyStartedAt).TotalSeconds
    }
    else {
        0
    }
    if (-not $proc.HasExited -and $elapsedSeconds -lt 20) {
        return
    }

    try {
        if ($script:ActiveProfileVerifyPollTimer) {
            $script:ActiveProfileVerifyPollTimer.Stop()
        }

        if (-not $proc.HasExited) {
            try { $proc.Kill() } catch {}
            throw "state --verify timed out after 20s"
        }

        $exitCode = $proc.ExitCode
        $rawOutput = Get-Content $script:ActiveProfileVerifyOutputFile -Raw -ErrorAction SilentlyContinue
        $errOutput = Get-Content $script:ActiveProfileVerifyErrorFile -Raw -ErrorAction SilentlyContinue
        if ($errOutput) { Write-TrayLog "State verification stderr: $errOutput" -Level "WARN" }
        if ($null -ne $exitCode -and $exitCode -ne 0) {
            throw "state --verify failed with exit code $exitCode"
        }
        if (-not $rawOutput) { throw "state --verify returned no output" }

        $json = Invoke-JsonSafe -Text $rawOutput -Source 'StateVerify'
        Apply-ActiveProfileVerificationJson -Json $json -Silent:([bool]$script:ActiveProfileVerifySilent)
    }
    catch {
        Write-TrayLog "State verification refresh failed: $($_.Exception.Message)" -Level "WARN"
        Set-ActiveProfileVerificationFailureAction -Reason "$($_.Exception.Message)"
    }
    finally {
        Stop-ActiveProfileVerificationRuntime
        Update-MenuState
    }
}

function Start-ActiveProfileVerificationTimer {
    param([int]$DelayMilliseconds = 1500)

    if ($script:ActiveProfileVerifyTimer) {
        try { $script:ActiveProfileVerifyTimer.Stop(); $script:ActiveProfileVerifyTimer.Dispose() } catch {}
        $script:ActiveProfileVerifyTimer = $null
    }
    if ([string]::IsNullOrWhiteSpace([string]$script:activeProfile)) { return }

    $timer = New-Object System.Windows.Forms.Timer
    $timer.Interval = [Math]::Max(250, $DelayMilliseconds)
    $timer.Add_Tick({
        try {
            $script:ActiveProfileVerifyTimer.Stop()
            $script:ActiveProfileVerifyTimer.Dispose()
        } catch {}
        $script:ActiveProfileVerifyTimer = $null
        Refresh-ActiveProfileVerificationState -Silent
    })
    $script:ActiveProfileVerifyTimer = $timer
    $timer.Start()
}

# ============================================================================
# NOTIFICATION SYSTEM
# ============================================================================

$script:EnableBalloonNotifications = $true
$script:NotificationTooltipRestoreTimer = $null
$script:NotificationTooltipRestoreDelayMs = 4500

function Set-NotifyIconTooltipText {
    param([AllowNull()][string]$Text)

    if (-not $script:notifyIcon) { return }

    $tooltipText = if ([string]::IsNullOrWhiteSpace($Text)) { "computa" } else { $Text.Trim() }
    if ($tooltipText.Length -gt 63) {
        $tooltipText = $tooltipText.Substring(0, 60) + "..."
    }
    $script:notifyIcon.Text = $tooltipText
}

function Get-TrayStateTooltipText {
    $activeRecord = Get-ActiveTrayProfileRecord
    if ($activeRecord.Id) {
        $profileName = if (
            $activeRecord.InCatalog -and
            $activeRecord.Profile -and
            -not [string]::IsNullOrWhiteSpace("$($activeRecord.Profile.Name)")
        ) {
            Format-TrayDisplayCopy -Text "$($activeRecord.Profile.Name)"
        }
        else {
            "$($activeRecord.DisplayName)"
        }
        $pendingApplyText = Get-ActiveProfilePendingApplyText
        $rebootPendingText = Get-ActiveProfileRebootPendingText
        if ($pendingApplyText) {
            if ($script:ActiveProfileVerificationStatus -eq "mismatch") {
                return "computa - Profile mismatch: $profileName"
            }
            return "computa - Pending profile fix: $profileName"
        }
        if ($rebootPendingText) {
            return "computa - Windows restart required: $profileName"
        }
        if (Get-ActiveProfileVerificationInProgressText) {
            return "computa - Checking profile state: $profileName"
        }
    }
    if ($activeRecord.Id -and $activeRecord.InCatalog) {
        $p = $activeRecord.Profile
        return "computa - $(Get-TrayProfileObjectDisplayName -Profile $p -Fallback $activeRecord.Id)"
    }
    if ($activeRecord.Id) {
        return "computa - Profile missing from current list: $($activeRecord.DisplayName)"
    }
    return "computa - Ready"
}

function Restore-TrayTooltipFromState {
    param([switch]$Force)

    if ($script:NotificationTooltipRestoreTimer -and -not $Force) { return }
    Set-NotifyIconTooltipText -Text (Get-TrayStateTooltipText)
}

function Stop-NotificationTooltipRestoreTimer {
    if ($script:NotificationTooltipRestoreTimer) {
        try { $script:NotificationTooltipRestoreTimer.Stop() } catch {}
        try { $script:NotificationTooltipRestoreTimer.Dispose() } catch {}
        $script:NotificationTooltipRestoreTimer = $null
    }
}

function Start-NotificationTooltipRestoreTimer {
    if (-not $script:notifyIcon) { return }
    Stop-NotificationTooltipRestoreTimer
    $timer = New-Object System.Windows.Forms.Timer
    $timer.Interval = $script:NotificationTooltipRestoreDelayMs
    $timer.Add_Tick({
        Stop-NotificationTooltipRestoreTimer
        Restore-TrayTooltipFromState -Force
    })
    $script:NotificationTooltipRestoreTimer = $timer
    $timer.Start()
}

function Set-TrayOperationTooltipText {
    param([AllowNull()][string]$Text)

    Stop-NotificationTooltipRestoreTimer
    Set-NotifyIconTooltipText -Text $Text
}

function Set-TransientNotificationTooltip {
    param(
        [string]$Title,
        [string]$Message
    )

    Set-NotifyIconTooltipText -Text "$Title - $Message"
    Start-NotificationTooltipRestoreTimer
}

function Show-TrayToast {
    param(
        [string]$Title = "computa",
        [string]$Message = "",
        [ValidateSet("Info","Warning","Error","Success")]
        [string]$Type = "Info",
        [int]$Duration = 4500,
        [string]$MetaText = "",
        [switch]$BypassDedup,
        [string]$ProfileGameGroup = "",
        [string]$ProfileCategory = "Other",
        [System.Drawing.Color]$ProfileColor = [System.Drawing.Color]::Empty,
        [switch]$ProfileActiveBadge,
        [string]$ProfileModeBadge = "",
        [switch]$ProfileFavoriteBadge,
        [string]$ActionName = "",
        [System.Drawing.Color]$ActionColor = [System.Drawing.Color]::Empty,
        [object[]]$ActionButtons = @()
    )

    Set-TransientNotificationTooltip -Title $Title -Message $Message

    if ($script:EnableBalloonNotifications) {
        Show-ThemedToast `
            -Title $Title `
            -Message $Message `
            -Type $Type `
            -Duration $Duration `
            -MetaText $MetaText `
            -BypassDedup:$BypassDedup `
            -ProfileGameGroup $ProfileGameGroup `
            -ProfileCategory $ProfileCategory `
            -ProfileColor $ProfileColor `
            -ProfileActiveBadge:$ProfileActiveBadge `
            -ProfileModeBadge $ProfileModeBadge `
            -ProfileFavoriteBadge:$ProfileFavoriteBadge `
            -ActionName $ActionName `
            -ActionColor $ActionColor `
            -ActionButtons @($ActionButtons)
    }
}

function Show-Notification {
    param(
        [string]$Title,
        [string]$Message,
        [ValidateSet("Info", "Warning", "Error", "Success")]
        [string]$Type = "Info",
        [string]$MetaText = "",
        [string]$ProfileGameGroup = "",
        [string]$ProfileCategory = "Other",
        [System.Drawing.Color]$ProfileColor = [System.Drawing.Color]::Empty,
        [switch]$ProfileActiveBadge,
        [string]$ProfileModeBadge = "",
        [switch]$ProfileFavoriteBadge,
        [string]$ActionName = "",
        [System.Drawing.Color]$ActionColor = [System.Drawing.Color]::Empty,
        [object[]]$ActionButtons = @()
    )

    # Pass Type through verbatim. Prior versions mapped Success -> Info,
    # which meant every "successful apply" toast was rendering as the
    # blue Info variant instead of the green phosphor Success accent.
    $toastType = if ($Type -in @("Info","Warning","Error","Success")) { $Type } else { "Info" }
    Show-TrayToast `
        -Title $Title `
        -Message $Message `
        -Type $toastType `
        -MetaText $MetaText `
        -ProfileGameGroup $ProfileGameGroup `
        -ProfileCategory $ProfileCategory `
        -ProfileColor $ProfileColor `
        -ProfileActiveBadge:$ProfileActiveBadge `
        -ProfileModeBadge $ProfileModeBadge `
        -ProfileFavoriteBadge:$ProfileFavoriteBadge `
        -ActionName $ActionName `
        -ActionColor $ActionColor `
        -ActionButtons @($ActionButtons)
}

function Get-TrayToastActionValue {
    param(
        [AllowNull()][object]$Action,
        [string[]]$Names
    )

    if (-not $Action) { return $null }
    foreach ($name in @($Names)) {
        if ([string]::IsNullOrWhiteSpace($name)) { continue }
        if ($Action -is [hashtable] -and $Action.ContainsKey($name)) {
            return $Action[$name]
        }
        $prop = $Action.PSObject.Properties[$name]
        if ($prop) { return $prop.Value }
    }
    return $null
}

function New-TrayToastActionButton {
    param(
        [AllowNull()][string]$Kind,
        [AllowNull()][string]$Label,
        [AllowNull()][string]$ProfileName = "",
        [AllowNull()][string]$Executable = "",
        [AllowNull()][string]$Text = "",
        [AllowNull()][string]$Uri = ""
    )

    $safeKind = if ([string]::IsNullOrWhiteSpace($Kind)) { "" } else { "$Kind".Trim().ToLowerInvariant() }
    $safeLabel = if ([string]::IsNullOrWhiteSpace($Label)) { "" } else { "$Label".Trim() }
    if ([string]::IsNullOrWhiteSpace($safeKind) -or [string]::IsNullOrWhiteSpace($safeLabel)) {
        return $null
    }

    if ($safeKind -notin @(
        "open_nvidia_profile_inspector",
        "open_nvidia_control_panel",
        "copy_text",
        "open_windows_settings"
    )) {
        return $null
    }

    return [pscustomobject]@{
        Kind = $safeKind
        Type = $safeKind
        Label = $safeLabel
        ProfileName = if ([string]::IsNullOrWhiteSpace($ProfileName)) { "" } else { "$ProfileName".Trim() }
        Executable = if ([string]::IsNullOrWhiteSpace($Executable)) { "" } else { "$Executable".Trim() }
        Text = if ([string]::IsNullOrWhiteSpace($Text)) { "" } else { "$Text".Trim() }
        Uri = if ([string]::IsNullOrWhiteSpace($Uri)) { "" } else { "$Uri".Trim() }
    }
}

function Add-TrayToastActionButton {
    param(
        [System.Collections.Generic.List[object]]$Target,
        [AllowNull()][object]$Button
    )

    if (-not $Target -or -not $Button) { return }
    if ($Target.Count -ge 2) { return }

    $kind = Get-TrayToastActionValue -Action $Button -Names @("Kind", "kind", "Type", "type")
    $label = Get-TrayToastActionValue -Action $Button -Names @("Label", "label")
    $profileName = Get-TrayToastActionValue -Action $Button -Names @("ProfileName", "profile_name")
    $executable = Get-TrayToastActionValue -Action $Button -Names @("Executable", "executable")
    $text = Get-TrayToastActionValue -Action $Button -Names @("Text", "text")
    $uri = Get-TrayToastActionValue -Action $Button -Names @("Uri", "uri")
    $key = @("$kind", "$label", "$profileName", "$executable", "$text", "$uri") -join "|"

    foreach ($existing in @($Target)) {
        $existingKey = @(
            "$(Get-TrayToastActionValue -Action $existing -Names @("Kind", "kind", "Type", "type"))",
            "$(Get-TrayToastActionValue -Action $existing -Names @("Label", "label"))",
            "$(Get-TrayToastActionValue -Action $existing -Names @("ProfileName", "profile_name"))",
            "$(Get-TrayToastActionValue -Action $existing -Names @("Executable", "executable"))",
            "$(Get-TrayToastActionValue -Action $existing -Names @("Text", "text"))",
            "$(Get-TrayToastActionValue -Action $existing -Names @("Uri", "uri"))"
        ) -join "|"
        if ($existingKey -eq $key) { return }
    }

    [void]$Target.Add($Button)
}

function Set-TrayClipboardText {
    param([AllowNull()][string]$Text)

    if ([string]::IsNullOrWhiteSpace($Text)) { return $false }
    try {
        [System.Windows.Forms.Clipboard]::SetText("$Text")
        return $true
    }
    catch {
        Write-TrayLog "Clipboard write failed: $($_.Exception.Message)" -Level "WARN"
        return $false
    }
}

function Find-NvidiaProfileInspectorPath {
    $candidates = [System.Collections.Generic.List[string]]::new()

    foreach ($path in @(
        (Join-Path (Get-Location).Path "nvidiaProfileInspector.exe"),
        (Join-Path (Get-Location).Path "tools\nvidiaProfileInspector.exe"),
        (Join-Path (Get-Location).Path "tools\npi\nvidiaProfileInspector.exe"),
        (Join-Path $PSScriptRoot "tools\npi\nvidiaProfileInspector.exe")
    )) {
        if (-not [string]::IsNullOrWhiteSpace($path)) { [void]$candidates.Add($path) }
    }

    try {
        $scriptParent = Split-Path -Path $PSScriptRoot -Parent
        if ($scriptParent) {
            [void]$candidates.Add((Join-Path $scriptParent "tools\npi\nvidiaProfileInspector.exe"))
        }
    } catch {}

    if ($script:ProjectRoot) {
        foreach ($relative in @(
            "nvidiaProfileInspector.exe",
            "tools\nvidiaProfileInspector.exe",
            "tools\npi\nvidiaProfileInspector.exe"
        )) {
            [void]$candidates.Add((Join-Path $script:ProjectRoot $relative))
        }
    }

    if ($HOME) {
        [void]$candidates.Add((Join-Path $HOME "nvidiaProfileInspector\nvidiaProfileInspector.exe"))
        [void]$candidates.Add((Join-Path $HOME "Tools\nvidiaProfileInspector\nvidiaProfileInspector.exe"))
    }
    if ($env:ProgramFiles) {
        [void]$candidates.Add((Join-Path $env:ProgramFiles "nvidiaProfileInspector\nvidiaProfileInspector.exe"))
    }
    if (${env:ProgramFiles(x86)}) {
        [void]$candidates.Add((Join-Path ${env:ProgramFiles(x86)} "nvidiaProfileInspector\nvidiaProfileInspector.exe"))
    }
    if ($env:LOCALAPPDATA) {
        [void]$candidates.Add((Join-Path $env:LOCALAPPDATA "nvidiaProfileInspector\nvidiaProfileInspector.exe"))
    }

    foreach ($candidate in @($candidates)) {
        try {
            if (-not [string]::IsNullOrWhiteSpace($candidate) -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
                return (Resolve-Path -LiteralPath $candidate).Path
            }
        } catch {}
    }
    return $null
}

function Open-NvidiaControlPanelFromToast {
    $candidates = [System.Collections.Generic.List[string]]::new()
    if ($env:ProgramFiles) {
        [void]$candidates.Add((Join-Path $env:ProgramFiles "NVIDIA Corporation\Control Panel Client\nvcplui.exe"))
    }
    if (${env:ProgramFiles(x86)}) {
        [void]$candidates.Add((Join-Path ${env:ProgramFiles(x86)} "NVIDIA Corporation\Control Panel Client\nvcplui.exe"))
    }

    foreach ($candidate in @($candidates)) {
        try {
            if (-not [string]::IsNullOrWhiteSpace($candidate) -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
                Start-Process -FilePath $candidate
                return $true
            }
        } catch {}
    }

    try {
        Start-Process -FilePath "nvcplui.exe"
        return $true
    } catch {}

    try {
        Start-Process -FilePath "ms-settings:display-advancedgraphics"
        return $true
    } catch {}

    return $false
}

function Open-NvidiaProfileInspectorFromToast {
    param(
        [AllowNull()][string]$ProfileName,
        [AllowNull()][string]$Executable
    )

    $clipboardLines = [System.Collections.Generic.List[string]]::new()
    if (-not [string]::IsNullOrWhiteSpace($ProfileName)) {
        [void]$clipboardLines.Add("NVIDIA profile: $($ProfileName.Trim())")
    }
    if (-not [string]::IsNullOrWhiteSpace($Executable)) {
        [void]$clipboardLines.Add("Executable: $($Executable.Trim())")
    }
    $copied = $false
    if ($clipboardLines.Count -gt 0) {
        $copied = Set-TrayClipboardText -Text ($clipboardLines -join [Environment]::NewLine)
    }

    $npiPath = Find-NvidiaProfileInspectorPath
    if ($npiPath) {
        try {
            Start-Process -FilePath $npiPath -WorkingDirectory (Split-Path -LiteralPath $npiPath -Parent)
            $message = if ($copied) {
                "NPI opened. Profile and EXE were copied for the manual binding step."
            }
            else {
                "NPI opened. Add the game EXE to the NVIDIA profile, then apply again."
            }
            Show-Notification -Title "Manual NVIDIA step" -Message $message -Type "Info" -ActionName "NVIDIA" -ActionColor $script:Colors.AccentGreen
            return
        }
        catch {
            Write-TrayLog "Failed to open NPI from toast: $($_.Exception.Message)" -Level "WARN"
        }
    }

    if (Open-NvidiaControlPanelFromToast) {
        $message = if ($copied) {
            "NPI was not found. Opened NVIDIA settings instead; profile and EXE were copied."
        }
        else {
            "NPI was not found. Opened NVIDIA settings instead."
        }
        Show-Notification -Title "Manual NVIDIA step" -Message $message -Type "Warning" -ActionName "NVIDIA" -ActionColor $script:Colors.AccentAmber
        return
    }

    Show-Notification -Title "Manual NVIDIA step" -Message "NPI was not found and NVIDIA settings did not open. Install NPI, then apply again." -Type "Warning" -ActionName "NVIDIA" -ActionColor $script:Colors.AccentAmber
}

function Invoke-TrayToastAction {
    param([AllowNull()][object]$Action)

    if (-not $Action) { return }
    $kind = Get-TrayToastActionValue -Action $Action -Names @("Kind", "kind", "type", "Type")
    $kind = if ([string]::IsNullOrWhiteSpace($kind)) { "" } else { "$kind".Trim().ToLowerInvariant() }
    $profileName = Get-TrayToastActionValue -Action $Action -Names @("ProfileName", "profile_name")
    $executable = Get-TrayToastActionValue -Action $Action -Names @("Executable", "executable")

    switch ($kind) {
        "open_nvidia_profile_inspector" {
            Write-TrayLog "Toast action: open NVIDIA Profile Inspector"
            Open-NvidiaProfileInspectorFromToast -ProfileName "$profileName" -Executable "$executable"
        }
        "open_nvidia_control_panel" {
            Write-TrayLog "Toast action: open NVIDIA settings"
            if (-not (Open-NvidiaControlPanelFromToast)) {
                Show-Notification -Title "NVIDIA settings" -Message "NVIDIA settings did not open." -Type "Warning" -ActionName "NVIDIA" -ActionColor $script:Colors.AccentAmber
            }
        }
        "copy_text" {
            $text = Get-TrayToastActionValue -Action $Action -Names @("Text", "text")
            if ([string]::IsNullOrWhiteSpace($text)) { $text = "$executable" }
            if (Set-TrayClipboardText -Text "$text") {
                Show-Notification -Title "Copied" -Message "Copied to clipboard." -Type "Success" -ActionName "Copy" -ActionColor $script:Colors.AccentGreen
            }
        }
        "open_windows_settings" {
            $uri = Get-TrayToastActionValue -Action $Action -Names @("Uri", "uri")
            if (-not [string]::IsNullOrWhiteSpace($uri) -and "$uri" -like "ms-settings:*") {
                Write-TrayLog "Toast action: open Windows settings $uri"
                Start-Process -FilePath "$uri"
            }
        }
        default {
            Write-TrayLog "Ignored unsupported toast action kind: $kind" -Level "WARN"
        }
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

# Resolve the backend command at startup.
# Prefer the installed packaged backend so tray restarts use the deployed build.
# Fall back to source Python for development sessions.
$script:PythonExe = $null
$script:AbsoBackendArgsPrefix = @()
$installedBackend = Join-Path $env:LOCALAPPDATA "AdaptiveBattleStationOptimizer\computa.exe"
if (-not (Test-Path $installedBackend)) {
    # Pre-rebrand deploys shipped the backend as abso.exe; keep resolving it
    # until the next deploy migrates the install.
    $legacyBackend = Join-Path $env:LOCALAPPDATA "AdaptiveBattleStationOptimizer\abso.exe"
    if (Test-Path $legacyBackend) {
        $installedBackend = $legacyBackend
    }
}
if (Test-Path $installedBackend) {
    $script:PythonExe = $installedBackend
}
else {
    $script:AbsoBackendArgsPrefix = @("-m", "abso")
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
}

function Get-AbsoBackendArgs {
    param([string[]]$CommandArgs)

    $allArgs = @()
    if ($script:AbsoBackendArgsPrefix) {
        $allArgs += $script:AbsoBackendArgsPrefix
    }
    $allArgs += $CommandArgs
    return $allArgs
}

function Get-AbsoBackendCommandLine {
    param([string[]]$CommandArgs)

    return "$($script:PythonExe) $((Get-AbsoBackendArgs -CommandArgs $CommandArgs) -join ' ')"
}

$script:AppVersion = "2.5.0"

Write-TrayLog "ABSO backend resolved: $(Get-AbsoBackendCommandLine -CommandArgs @('--version'))"

function Get-TrayFileSha256 {
    <#
    .SYNOPSIS
    SHA256 of a file via .NET, without the Get-FileHash cmdlet.

    The wscript-launched hidden PowerShell host can fail to autoload
    Microsoft.PowerShell.Utility (observed on Canary builds), which makes
    Get-FileHash a CommandNotFoundException and silently blanked every hash
    in the runtime marker. Raw .NET needs no cmdlet resolution.
    #>
    param([string]$Path)

    $stream = [System.IO.File]::OpenRead($Path)
    try {
        $sha = [System.Security.Cryptography.SHA256]::Create()
        try {
            return ([System.BitConverter]::ToString($sha.ComputeHash($stream)) -replace "-", "").ToLowerInvariant()
        }
        finally {
            $sha.Dispose()
        }
    }
    finally {
        $stream.Dispose()
    }
}

function Write-TrayRuntimeMarker {
    <#
    .SYNOPSIS
    Records the script version/hash that this running tray host loaded.

    Health checks compare this marker with the installed sidecar script so a
    file deploy cannot be mistaken for a live tray restart.
    #>
    try {
        $appRoot = Join-Path ([Environment]::GetFolderPath("LocalApplicationData")) "AdaptiveBattleStationOptimizer"
        if (-not (Test-Path -LiteralPath $appRoot)) {
            New-Item -Path $appRoot -ItemType Directory -Force -ErrorAction Stop | Out-Null
        }
        $markerPath = Join-Path $appRoot "tray-runtime.json"
        $scriptPath = if (-not [string]::IsNullOrWhiteSpace($PSCommandPath)) {
            $PSCommandPath
        }
        else {
            Join-Path $script:ScriptDir "ABSO-Tray.ps1"
        }
        $scriptHash = $null
        $scriptLastWrite = $null
        try {
            $scriptHash = Get-TrayFileSha256 -Path $scriptPath
            $scriptLastWrite = [System.IO.File]::GetLastWriteTimeUtc($scriptPath).ToString("o")
        } catch {}

        $moduleHashes = [ordered]@{}
        foreach ($moduleName in @(
            "ABSO-Theme.ps1",
            "ABSO-ThemePack.ps1",
            "ABSO-Icons.ps1",
            "ABSO-Notifications.ps1",
            "ABSO-Settings.ps1",
            "ABSO-StartupState.ps1",
            "ABSO-QuickPanel.ps1"
        )) {
            $modulePath = Join-Path $script:ScriptDir $moduleName
            if (-not (Test-Path -LiteralPath $modulePath)) { continue }
            try {
                $moduleHashes[$moduleName] = [ordered]@{
                    path = $modulePath
                    hash_sha256 = Get-TrayFileSha256 -Path $modulePath
                    last_write_utc = [System.IO.File]::GetLastWriteTimeUtc($modulePath).ToString("o")
                }
            } catch {}
        }

        $payload = [ordered]@{
            version = $script:AppVersion
            pid = $PID
            started_at_utc = [DateTime]::UtcNow.ToString("o")
            script_path = $scriptPath
            script_hash_sha256 = $scriptHash
            script_last_write_utc = $scriptLastWrite
            module_hashes = $moduleHashes
            backend_command = Get-AbsoBackendCommandLine -CommandArgs @("--version")
        }
        $jsonText = $payload | ConvertTo-Json -Depth 6
        [System.IO.File]::WriteAllText($markerPath, $jsonText, $script:LogUtf8NoBom)
        Write-TrayLog "Tray runtime marker written: $markerPath"
    }
    catch {
        Write-TrayLog "Tray runtime marker write failed: $($_.Exception.Message)" -Level "WARN"
    }
}

Write-TrayRuntimeMarker

# ============================================================================
# PROFILE DEFINITIONS
# ============================================================================

$script:FallbackProfiles = [ordered]@{
    # --- Productivity ---
    "productivity" = @{
        Name     = "Desktop / Productivity"
        Sub      = "SDR | HDR OFF | Adaptive VSync | VRR"
        Cat      = "Desktop"
        Desc     = "Multi-monitor browsing and coding (SDR). Turns Windows HDR off."
        Exes     = @("Code.exe", "devenv.exe", "chrome.exe", "firefox.exe", "msedge.exe", "WindowsTerminal.exe", "idea64.exe")
        SyncMode = "agnostic"
        GameGroup = "productivity"
        GroupName = "Desktop / Productivity"
        Variant = "SDR"
        Rank = 10
    }

    # --- Fighting Games: Rivals 2 ---
    "rivals2-offline"   = @{
        Name     = "Rivals 2 - Offline No Sync"
        Sub      = "No Sync | LLM ON | Uncapped | Offline Only"
        Cat      = "Fighting"
        Desc     = "Latency-focused no-sync profile for training/local play (NOT for online)"
        Exes     = @("Rivals2-Win64-Shipping.exe", "RivalsofAether2.exe", "Rivals2.exe")
        SyncMode = "off"
    }
    "rivals2-online"    = @{
        Name     = "Rivals 2 - Online No Sync"
        Sub      = "No Sync | LLM ON | Rollback-Safe"
        Cat      = "Fighting"
        Desc     = "Stable rollback-safe settings for online play (prioritizes stability)"
        Exes     = @("Rivals2-Win64-Shipping.exe", "RivalsofAether2.exe", "Rivals2.exe")
        SyncMode = "off"
    }
    "rivals2-gsync" = @{
        Name     = "Rivals 2 - Offline GSYNC"
        Sub      = "G-SYNC ON | LLM ON | VSync Safety Net | Offline Only"
        Cat      = "Fighting"
        Desc     = "Low latency VRR profile (G-SYNC ON, VSync safety net)"
        Exes     = @("Rivals2-Win64-Shipping.exe", "RivalsofAether2.exe", "Rivals2.exe")
        SyncMode = "on"
    }
    "rivals2-online-gsync" = @{
        Name     = "Rivals 2 - Online GSYNC"
        Sub      = "G-SYNC ON | LLM ON | Rollback-Safe"
        Cat      = "Fighting"
        Desc     = "Rollback-safe VRR profile (G-SYNC ON, stability-focused)"
        Exes     = @("Rivals2-Win64-Shipping.exe", "RivalsofAether2.exe", "Rivals2.exe")
        SyncMode = "on"
    }

    # --- Fighting Games: Melee ---
    "slippi-melee"      = @{
        Name     = "Super Smash Bros. Melee (Slippi)"
        Sub      = "Competitive | No Sync | Backend-Aware"
        Cat      = "Fighting"
        Desc     = "Latency-focused no-sync profile for competitive Melee"
        Exes     = @("Slippi Dolphin.exe", "Dolphin.exe")
        SyncMode = "off"
    }
    "slippi-melee-console-parity" = @{
        Name     = "Super Smash Bros. Melee (Slippi Console-Parity)"
        Sub      = "Console-Parity | 60Hz + VSync | LLM OFF"
        Cat      = "Fighting"
        Desc     = "Console-like frame pacing and presentation for offline practice"
        Exes     = @("Slippi Dolphin.exe", "Dolphin.exe")
        SyncMode = "on"
    }
    "slippi-melee-universal" = @{
        Name     = "Super Smash Bros. Melee (Slippi Universal)"
        Sub      = "No Sync | HAGS ON | Reapply-Friendly"
        Cat      = "Fighting"
        Desc     = "No-sync Slippi profile with HAGS kept on so re-applying does not require a reboot. VSync OFF, G-SYNC/VRR OFF."
        Exes     = @("Slippi Dolphin.exe", "Dolphin.exe")
        SyncMode = "off"
    }

    # --- Fighting Games: SSBU ---
    "ryujinx-ssbu"      = @{
        Name     = "SSBU / HewDraw Remix (Ryujinx)"
        Sub      = "Vulkan | Fixed 60fps | HAGS ON | LLM OFF"
        Cat      = "Fighting"
        Desc     = "Latency-focused no-sync profile for competitive SSBU/HDR"
        Exes     = @("Ryujinx.exe", "Ryujinx.Ava.exe", "Ryujinx.Headless.SDL2.exe", "Ryubing.exe")
        SyncMode = "off"
    }

    # --- ARPG ---
    "diablo4"           = @{
        Name     = "Diablo 4 - HDR"
        Sub      = "HDR ON | Reflex ON | G-SYNC ON | LLM OFF"
        Cat      = "RPGs"
        Desc     = "Balanced Diablo 4 HDR profile with native LocalPrefs enforcement for Reflex, HDR, and VRR"
        Exes     = @("Diablo IV.exe")
        SyncMode = "on"
    }
    "diablo4-sdr"       = @{
        Name     = "Diablo 4 - SDR"
        Sub      = "SDR | Reflex ON | VRR"
        Cat      = "RPGs"
        Desc     = "Balanced Diablo 4 SDR profile with native LocalPrefs enforcement for Reflex and VRR"
        Exes     = @("Diablo IV.exe")
        SyncMode = "on"
    }

    # --- Shooter ---
    "fortnite"          = @{
        Name     = "Fortnite - SDR"
        Sub      = "SDR | Reflex (set in-game) | No Sync"
        Cat      = "Shooters"
        Desc     = "Competitive SDR Fortnite profile with a no-sync latency path. Keeps driver LLM off for Reflex; enable Reflex On + Boost in-game."
        Exes     = @(
            "FortniteClient-Win64-Shipping.exe",
            "FortniteClient-Win64-Shipping_EAC.exe",
            "FortniteClient-Win64-Shipping_BE.exe",
            "FortniteClient-Win64-Shipping_EAC_EOS.exe"
        )
        SyncMode = "off"
    }
    "fortnite-hdr"      = @{
        Name     = "Fortnite - HDR"
        Sub      = "HDR ON | Reflex (set in-game) | No Sync"
        Cat      = "Shooters"
        Desc     = "Competitive Fortnite HDR profile with a no-sync latency path. Keeps driver LLM off for Reflex; enable Reflex On + Boost in-game."
        Exes     = @(
            "FortniteClient-Win64-Shipping.exe",
            "FortniteClient-Win64-Shipping_EAC.exe",
            "FortniteClient-Win64-Shipping_BE.exe",
            "FortniteClient-Win64-Shipping_EAC_EOS.exe"
        )
        SyncMode = "off"
    }
    "marvel-rivals-sdr" = @{
        Name     = "Marvel Rivals - SDR"
        Sub      = "SDR | Reflex ON+Boost | G-SYNC ON"
        Cat      = "Shooters"
        Desc     = "Performance-first SDR Marvel Rivals profile. Uses Reflex + VRR and expects you to A/B the in-game Performance Optimization (Beta) toggle on your hardware."
        Exes     = @("Marvel.exe", "Marvel-Win64-Shipping.exe")
        SyncMode = "on"
    }
    "marvel-rivals-hdr" = @{
        Name     = "Marvel Rivals - HDR"
        Sub      = "HDR ON | Reflex ON+Boost | G-SYNC ON"
        Cat      = "Shooters"
        Desc     = "Performance-first HDR Marvel Rivals profile. Uses Reflex + VRR and expects you to A/B the in-game Performance Optimization (Beta) toggle on your hardware."
        Exes     = @("Marvel.exe", "Marvel-Win64-Shipping.exe")
        SyncMode = "on"
    }
    "overwatch2"        = @{
        Name     = "Overwatch 2 - No Sync SDR"
        Sub      = "No Sync SDR | Reflex OFF | VSync OFF | G-SYNC OFF"
        Cat      = "Shooters"
        Desc     = "Latency-focused no-sync SDR profile (Reflex OFF, VSync OFF, VRR OFF)"
        Exes     = @("Overwatch.exe")
        SyncMode = "off"
    }
    "overwatch2-hdr"    = @{
        Name     = "Overwatch 2 - No Sync HDR"
        Sub      = "No Sync HDR | Reflex OFF | VSync OFF | G-SYNC OFF"
        Cat      = "Shooters"
        Desc     = "Latency-focused no-sync HDR profile. Native HDR for OLED / Mini-LED displays; same sync/VRR contract as the SDR variant."
        Exes     = @("Overwatch.exe")
        SyncMode = "off"
    }
    "overwatch2-gsync"  = @{
        Name     = "Overwatch 2 - GSYNC SDR"
        Sub      = "Overlay-Free SDR Borderless | Reflex (set in-game) | G-SYNC ON"
        Cat      = "Shooters"
        Desc     = "Low-latency Overwatch 2 G-SYNC on the optimized borderless VRR path, while stopping capture and overlay processes."
        Exes     = @("Overwatch.exe")
        SyncMode = "on"
    }
    "overwatch2-gsync-hdr" = @{
        Name     = "Overwatch 2 - GSYNC HDR"
        Sub      = "Overlay-Free HDR Borderless | Reflex (set in-game) | G-SYNC ON"
        Cat      = "Shooters"
        Desc     = "Low-latency native-HDR Overwatch 2 G-SYNC on the optimized borderless VRR path, while stopping capture and overlay processes."
        Exes     = @("Overwatch.exe")
        SyncMode = "on"
    }

    # --- Browser Games ---
    "pokemon-auto-chess" = @{
        Name     = "Pokemon Auto Chess"
        Sub      = "LLM ON | Browser WebGL"
        Cat      = "Other"
        Desc     = "WebGL browser game optimization for stable performance"
        Exes     = @("chrome.exe", "msedge.exe", "firefox.exe", "brave.exe")
        SyncMode = "agnostic"
    }
    "pacdeluxe"         = @{
        Name     = "PACDeluxe (Pokemon Auto Chess)"
        Sub      = "LLM ON | Tauri + WebView2 | Adaptive VSync"
        Cat      = "Other"
        Desc     = "Native Tauri client optimization for smooth WebGL auto-battler gameplay"
        Exes     = @("pac-deluxe.exe", "msedgewebview2.exe")
        SyncMode = "agnostic"
    }
}

foreach ($fallbackProfile in @($script:FallbackProfiles.Values)) {
    if (-not $fallbackProfile) { continue }
    foreach ($copyField in @("Name", "Sub", "Desc", "GroupName", "Variant")) {
        if ($fallbackProfile.ContainsKey($copyField)) {
            $fallbackProfile[$copyField] = Format-TrayDisplayCopy -Text "$($fallbackProfile[$copyField])"
        }
    }
}

$script:Profiles = [ordered]@{}
foreach ($id in $script:FallbackProfiles.Keys) {
    $script:Profiles[$id] = $script:FallbackProfiles[$id]
}
$script:ProfileCatalogCacheFile = Join-Path $script:ScriptDir "profile-catalog-cache.json"
$script:ProfileCatalogLastSource = $null
$script:ProfileCatalogLastCount = 0
$script:ProfileCatalogUsedFallback = $false

function Get-CategoryFromOptimizationTarget {
    param([string]$OptimizationTarget)

    $target = if ($null -eq $OptimizationTarget) { "" } else { "$OptimizationTarget" }
    switch ($target.ToLowerInvariant()) {
        "productivity" { return "Desktop" }
        "low_latency_high_fps" { return "Shooters" }
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

function Normalize-TrayCategory {
    param([string]$Category)

    switch ("$Category") {
        "Productivity" { return "Desktop" }
        "Shooter" { return "Shooters" }
        "ARPG" { return "RPGs" }
        "Streaming" { return "Other" }
        default {
            if ([string]::IsNullOrWhiteSpace("$Category")) { return "Other" }
            return "$Category"
        }
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

        $rawName = if ($entry.display_name) { "$($entry.display_name)" } elseif ($fallback) { "$($fallback.Name)" } else { $id }
        $rawSub = if ($entry.tray_subtitle) { "$($entry.tray_subtitle)" } elseif ($fallback) { "$($fallback.Sub)" } else { "Profile" }
        $name = Format-TrayDisplayCopy -Text $rawName
        $sub = Format-TrayDisplayCopy -Text $rawSub
        $cat = if ($entry.tray_category) {
            "$($entry.tray_category)"
        }
        elseif ($fallback) {
            "$($fallback.Cat)"
        }
        else {
            Get-CategoryFromOptimizationTarget -OptimizationTarget "$($entry.optimization_target)"
        }
        $cat = Normalize-TrayCategory -Category $cat
        $rawDesc = if ($entry.tray_description) {
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

        $gameGroup = if ($entry.tray_group) {
            "$($entry.tray_group)"
        } elseif ($fallback -and $fallback.GameGroup) {
            "$($fallback.GameGroup)"
        } else {
            $id
        }
        $rawGroupName = if ($entry.tray_group_name) {
            "$($entry.tray_group_name)"
        } elseif ($fallback -and $fallback.GroupName) {
            "$($fallback.GroupName)"
        } else {
            $name
        }
        $groupName = Format-TrayDisplayCopy -Text $rawGroupName
        $rawVariant = if ($entry.tray_variant) {
            "$($entry.tray_variant)"
        } elseif ($fallback -and $fallback.Variant) {
            "$($fallback.Variant)"
        } else {
            $name
        }
        $variant = Format-TrayDisplayCopy -Text $rawVariant
        $rank = if ($null -ne $entry.tray_rank) {
            try { [int]$entry.tray_rank } catch { 100 }
        } elseif ($fallback -and $fallback.Rank) {
            try { [int]$fallback.Rank } catch { 100 }
        } else {
            100
        }
        $trayVisible = $true
        if ($null -ne $entry.tray_visible) {
            try { $trayVisible = [bool]$entry.tray_visible } catch { $trayVisible = $true }
        } elseif ($fallback -and $null -ne $fallback.TrayVisible) {
            try { $trayVisible = [bool]$fallback.TrayVisible } catch { $trayVisible = $true }
        }
        # Per-machine curation: tray-config hiddenProfiles wins over catalog
        # visibility, so users can slim the menu without patching the catalog.
        if ($trayVisible -and $script:TrayConfig -and $script:TrayConfig.hiddenProfiles) {
            if (@($script:TrayConfig.hiddenProfiles) -contains $id) {
                $trayVisible = $false
            }
        }

        # Launch-time process janitor killset comes from the Python catalog
        # so the tray never has to hardcode game-specific overlay/sync lists.
        # Both tiers default to empty arrays when the catalog entry is older
        # than the launch-sanitizer feature.
        $alwaysSafe = @()
        $optIn = @()
        if ($entry.launch_process_killset) {
            if ($entry.launch_process_killset.always_safe) {
                foreach ($img in @($entry.launch_process_killset.always_safe)) {
                    if (-not [string]::IsNullOrWhiteSpace("$img")) {
                        $alwaysSafe += "$img"
                    }
                }
            }
            if ($entry.launch_process_killset.opt_in) {
                foreach ($img in @($entry.launch_process_killset.opt_in)) {
                    if (-not [string]::IsNullOrWhiteSpace("$img")) {
                        $optIn += "$img"
                    }
                }
            }
        }

        $requiresOverlayFree = $false
        if ($null -ne $entry.requires_overlay_free_path) {
            try { $requiresOverlayFree = [bool]$entry.requires_overlay_free_path } catch {}
        }

        $keepAwakeWhileGaming = $false
        if ($null -ne $entry.keep_awake_while_gaming) {
            try { $keepAwakeWhileGaming = [bool]$entry.keep_awake_while_gaming } catch {}
        }

        $isOnlineProfile = $false
        if ($null -ne $entry.is_online_profile) {
            try { $isOnlineProfile = [bool]$entry.is_online_profile } catch {}
        }

        $profiles[$id] = @{
            Name                  = $name
            Sub                   = $sub
            Cat                   = $cat
            Desc                  = $desc
            Exes                  = $exeHints
            SyncMode              = $syncMode
            OptTarget             = $optTarget
            GameGroup             = $gameGroup
            GroupName             = $groupName
            Variant               = $variant
            Rank                  = $rank
            TrayVisible           = $trayVisible
            KillsetAlwaysSafe     = $alwaysSafe
            KillsetOptIn          = $optIn
            RequiresOverlayFree   = $requiresOverlayFree
            KeepAwakeWhileGaming  = $keepAwakeWhileGaming
            IsOnline              = $isOnlineProfile
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

function Read-ProfileAliasMapFromCache {
    $aliases = @{}
    if (-not $script:ProfileCatalogCacheFile -or -not (Test-Path $script:ProfileCatalogCacheFile)) {
        return $aliases
    }

    try {
        $cacheRaw = Get-Content $script:ProfileCatalogCacheFile -Raw -ErrorAction Stop
        if (-not $cacheRaw) { return $aliases }
        $cachePayload = $cacheRaw | ConvertFrom-Json
        if ($cachePayload -and $cachePayload.aliases) {
            $cachePayload.aliases.PSObject.Properties | ForEach-Object {
                $aliases[$_.Name] = "$($_.Value)"
            }
        }
    }
    catch {
        Write-TrayLog "Profile alias cache read failed: $($_.Exception.Message)" -Level "WARN"
    }

    return $aliases
}

function Write-ProfileCatalogCache {
    param(
        [object[]]$Entries,
        [hashtable]$Aliases = $null
    )

    if (-not $script:ProfileCatalogCacheFile -or -not $Entries -or $Entries.Count -eq 0) {
        return $false
    }

    # Preserve existing aliases when caller didn't supply a fresh map.
    if ($null -eq $Aliases) {
        $Aliases = Read-ProfileAliasMapFromCache
    }

    $aliasOrdered = [ordered]@{}
    if ($Aliases) {
        foreach ($key in ($Aliases.Keys | Sort-Object)) {
            $aliasOrdered[$key] = "$($Aliases[$key])"
        }
    }

    try {
        if (Test-Path $script:ProfileCatalogCacheFile) {
            $existingEntries = Read-ProfileCatalogCacheEntries
            $existingAliases = Read-ProfileAliasMapFromCache
            $existingAliasOrdered = [ordered]@{}
            if ($existingAliases) {
                foreach ($key in ($existingAliases.Keys | Sort-Object)) {
                    $existingAliasOrdered[$key] = "$($existingAliases[$key])"
                }
            }

            $existingProfilesJson = ConvertTo-Json -InputObject @($existingEntries) -Depth 8 -Compress
            $newProfilesJson = ConvertTo-Json -InputObject @($Entries) -Depth 8 -Compress
            $existingAliasesJson = ConvertTo-Json -InputObject $existingAliasOrdered -Depth 8 -Compress
            $newAliasesJson = ConvertTo-Json -InputObject $aliasOrdered -Depth 8 -Compress

            if ($existingProfilesJson -eq $newProfilesJson -and $existingAliasesJson -eq $newAliasesJson) {
                Write-TrayLog "Profile catalog cache unchanged; skipping write"
                return $false
            }
        }

        $payload = [ordered]@{
            version = 2
            saved_at = (Get-Date).ToString("o")
            profiles = @($Entries)
            aliases = $aliasOrdered
        }
        $dir = Split-Path -Parent $script:ProfileCatalogCacheFile
        if ($dir -and -not (Test-Path $dir)) {
            New-Item -Path $dir -ItemType Directory -Force | Out-Null
        }
        # Use .NET WriteAllText to avoid UTF-8 BOM (PowerShell 5.1 Set-Content adds BOM)
        $jsonText = $payload | ConvertTo-Json -Depth 8
        [System.IO.File]::WriteAllText($script:ProfileCatalogCacheFile, $jsonText, [System.Text.UTF8Encoding]::new($false))
        return $true
    }
    catch {
        Write-TrayLog "Profile catalog cache write failed: $($_.Exception.Message)" -Level "WARN"
    }
    return $false
}

function Resolve-ProfileAlias {
    <#
    .SYNOPSIS
    Map a potentially-retired profile id to its canonical replacement.

    Returns $null when passed a null/empty id, otherwise returns the alias
    target if one exists or the input id unchanged.
    #>
    param([string]$ProfileId)

    if ([string]::IsNullOrWhiteSpace($ProfileId)) {
        return $null
    }
    if ($script:ProfileAliases -and $script:ProfileAliases.ContainsKey($ProfileId)) {
        return $script:ProfileAliases[$ProfileId]
    }
    return $ProfileId
}

function Normalize-TrayConfigProfileIds {
    <#
    .SYNOPSIS
    Resolve retired profile ids in the tray config through the alias map.

    Walks favorites, defaultProfile, recentProfiles, profileHistory,
    lastProfileState, and lastStartupResolution. Returns a tuple-like
    object: @{ Config = <normalized>; Changed = <bool> }.
    Caller is responsible for persisting if Changed is true.
    #>
    param([hashtable]$Config)

    if (-not $Config) {
        return @{ Config = $Config; Changed = $false }
    }

    $changed = $false

    if ($Config.favorites) {
        $normalized = @()
        $seen = @{}
        foreach ($id in $Config.favorites) {
            $resolved = Resolve-ProfileAlias $id
            if ([string]::IsNullOrWhiteSpace($resolved)) { continue }
            if ($resolved -ne $id) { $changed = $true }
            if (-not $seen.ContainsKey($resolved)) {
                $normalized += $resolved
                $seen[$resolved] = $true
            }
            else {
                $changed = $true
            }
        }
        $Config.favorites = @($normalized)
    }

    if ($Config.defaultProfile) {
        $resolved = Resolve-ProfileAlias $Config.defaultProfile
        if ($resolved -ne $Config.defaultProfile) {
            $Config.defaultProfile = $resolved
            $changed = $true
        }
    }

    foreach ($listKey in @("recentProfiles", "profileHistory")) {
        if (-not $Config.$listKey) { continue }
        $items = @($Config.$listKey)
        $updated = @()
        foreach ($entry in $items) {
            if ($null -eq $entry) { continue }
            $entryId = $null
            if ($entry -is [hashtable]) {
                $entryId = $entry["id"]
            }
            elseif ($entry.PSObject.Properties["id"]) {
                $entryId = $entry.id
            }
            if ($entryId) {
                $resolved = Resolve-ProfileAlias $entryId
                if ($resolved -ne $entryId) {
                    if ($entry -is [hashtable]) {
                        $entry["id"] = $resolved
                    }
                    else {
                        $entry | Add-Member -NotePropertyName "id" -NotePropertyValue $resolved -Force
                    }
                    $changed = $true
                }
            }
            $updated += $entry
        }
        $Config.$listKey = @($updated)
    }

    foreach ($stateKey in @("lastProfileState", "lastStartupResolution")) {
        $state = $Config.$stateKey
        if ($null -eq $state) { continue }
        $stateId = $null
        if ($state -is [hashtable]) {
            $stateId = $state["id"]
        }
        elseif ($state.PSObject.Properties["id"]) {
            $stateId = $state.id
        }
        if ($stateId) {
            $resolved = Resolve-ProfileAlias $stateId
            if ($resolved -ne $stateId) {
                if ($state -is [hashtable]) {
                    $state["id"] = $resolved
                }
                else {
                    $state | Add-Member -NotePropertyName "id" -NotePropertyValue $resolved -Force
                }
                $changed = $true
            }
        }
    }

    return @{ Config = $Config; Changed = $changed }
}

function Fetch-ProfileAliasMapFromCli {
    if (-not $script:PythonExe) { return $null }

    try {
        $tempFile = [System.IO.Path]::GetTempFileName()
        $errFile = "$tempFile.err"
        $proc = Start-Process -FilePath $script:PythonExe -ArgumentList (Get-AbsoBackendArgs -CommandArgs @("profile-aliases", "--json")) `
            -NoNewWindow -PassThru -WorkingDirectory $script:ProjectRoot `
            -RedirectStandardOutput $tempFile -RedirectStandardError $errFile
        # PS 5.1: cache the handle now or .ExitCode reads $null after exit.
        if ($proc) { $null = $proc.Handle }
        # WaitForExit(timeout) returns Boolean; [void] prevents it from polluting
        # the function's output stream (which would turn the returned hashtable
        # into a 2-element Object[] array).
        [void]$proc.WaitForExit(10000)
        if (-not $proc.HasExited) {
            Write-TrayLog "Profile alias refresh timed out after 10s, killing process" -Level "WARN"
            $proc.Kill()
        }
        $exitCode = $proc.ExitCode
        $proc.Dispose()

        $raw = Get-Content $tempFile -Raw -ErrorAction SilentlyContinue
        Remove-Item $tempFile -Force -ErrorAction SilentlyContinue
        Remove-Item $errFile -Force -ErrorAction SilentlyContinue

        if (($null -eq $exitCode -or $exitCode -eq 0) -and $raw) {
            $payload = $raw | ConvertFrom-Json
            if ($payload -and $payload.success -and $payload.data) {
                $map = @{}
                $payload.data.PSObject.Properties | ForEach-Object {
                    $map[$_.Name] = "$($_.Value)"
                }
                return $map
            }
        }
    }
    catch {
        Write-TrayLog "Profile alias refresh failed from CLI: $($_.Exception.Message)" -Level "WARN"
    }

    return $null
}

function Invoke-CliCatalogRefresh {
    <#
    .SYNOPSIS
    Blocking CLI catalog fetch; returns a hashtable with Entries + AliasMap.

    Extracted from Initialize-ProfilesFromCliCatalog so the same logic can run
    either at startup (cold-cache fallback) or in a deferred background
    refresh. Returns a hashtable rather than a tuple/array because PowerShell's
    @(...) array-subexpression flattens nested arrays - returning
    @(,$entries, $aliasMap) silently collapsed entries+alias into a single
    flat list when callers indexed it.
    #>
    $entries = @()
    $aliasMap = $null

    if (-not $script:PythonExe) {
        Write-TrayLog "Python executable unavailable for profile catalog refresh" -Level "WARN"
        return @{ Entries = $entries; AliasMap = $aliasMap }
    }

    try {
        $tempFile = [System.IO.Path]::GetTempFileName()
        $errFile = "$tempFile.err"
        $proc = Start-Process -FilePath $script:PythonExe -ArgumentList (Get-AbsoBackendArgs -CommandArgs @("profiles", "--json")) `
            -NoNewWindow -PassThru -WorkingDirectory $script:ProjectRoot `
            -RedirectStandardOutput $tempFile -RedirectStandardError $errFile
        # PS 5.1: cache the handle now or .ExitCode reads $null after exit.
        if ($proc) { $null = $proc.Handle }

        $proc.WaitForExit(15000)
        if (-not $proc.HasExited) {
            Write-TrayLog "Profile catalog refresh timed out after 15s, killing process" -Level "WARN"
            $proc.Kill()
        }
        $exitCode = $proc.ExitCode
        $proc.Dispose()

        $raw = Get-Content $tempFile -Raw -ErrorAction SilentlyContinue
        $errOutput = Get-Content $errFile -Raw -ErrorAction SilentlyContinue
        Remove-Item $tempFile -Force -ErrorAction SilentlyContinue
        Remove-Item $errFile -Force -ErrorAction SilentlyContinue
        if ($errOutput) {
            Write-TrayLog "Profile catalog stderr: $errOutput" -Level "WARN"
        }

        $exitCodeOk = ($null -eq $exitCode -or $exitCode -eq 0)
        if ($exitCodeOk -and $raw) {
            $payload = $raw | ConvertFrom-Json
            if ($payload -and $payload.success -and $payload.data) {
                $entries = @($payload.data)
                $aliasMap = Fetch-ProfileAliasMapFromCli
            }
            else {
                Write-TrayLog "Profile catalog payload missing/invalid from CLI" -Level "WARN"
            }
        }
        else {
            Write-TrayLog "Profile catalog refresh skipped from CLI (exit=$exitCode)" -Level "WARN"
        }
    }
    catch {
        Write-TrayLog "Profile catalog refresh failed from CLI: $($_.Exception.Message)" -Level "WARN"
    }

    return @{ Entries = $entries; AliasMap = $aliasMap }
}


function Start-BackgroundCatalogRefresh {
    <#
    .SYNOPSIS
    Deferred (non-blocking-at-startup) refresh of the profile catalog cache.

    Schedules a one-shot WinForms Timer that fires ~3s after startup.
    The refresh itself uses the same Invoke-CliCatalogRefresh path the
    cold-start fallback uses, then writes the result to disk so the
    NEXT tray start picks it up immediately.

    Why a WinForms Timer instead of Start-Job: Start-Job spawns a fresh
    PowerShell process whose working directory / env vars / admin context
    don't always inherit cleanly, causing the cache write to silently
    fail. The Timer runs in this tray's own process, so $script:PythonExe
    / $script:ProjectRoot / $script:ProfileCatalogCacheFile are all the
    same values that worked at cold-start fallback. The 1-2s UI-thread
    block during the CLI call is acceptable because it fires AFTER the
    user-visible startup is complete and the user is unlikely to be
    interacting with the menu in the first ~5 seconds.

    Stale-while-revalidate pattern: snappy UX now, freshness guaranteed
    on subsequent starts.
    #>
    if (-not $script:PythonExe -or -not $script:ProfileCatalogCacheFile) {
        return
    }
    if ($script:BackgroundCatalogTimer) {
        try { $script:BackgroundCatalogTimer.Stop(); $script:BackgroundCatalogTimer.Dispose() } catch {}
        $script:BackgroundCatalogTimer = $null
    }
    try {
        $script:BackgroundCatalogTimer = New-Object System.Windows.Forms.Timer
        $script:BackgroundCatalogTimer.Interval = 3000
        $script:BackgroundCatalogTimer.Add_Tick({
            try {
                $this.Stop()
                $this.Dispose()
            } catch {}
            $script:BackgroundCatalogTimer = $null
            try {
                $sw = [System.Diagnostics.Stopwatch]::StartNew()
                $result = Invoke-CliCatalogRefresh
                $entries = $result.Entries
                $aliasMap = $result.AliasMap
                if ($entries -and $entries.Count -gt 0) {
                    $wroteCache = [bool](Write-ProfileCatalogCache -Entries $entries -Aliases $aliasMap)
                    $sw.Stop()
                    if ($wroteCache) {
                        Write-TrayLog "Background catalog refresh wrote cache ($($entries.Count) profiles) in $($sw.ElapsedMilliseconds)ms" -Level "INFO"
                    }
                    else {
                        Write-TrayLog "Background catalog refresh verified cache current ($($entries.Count) profiles) in $($sw.ElapsedMilliseconds)ms" -Level "INFO"
                    }
                } else {
                    Write-TrayLog "Background catalog refresh returned empty - cache unchanged" -Level "WARN"
                }
            } catch {
                Write-TrayLog "Background catalog refresh failed: $($_.Exception.Message)" -Level "WARN"
            }
        })
        $script:BackgroundCatalogTimer.Start()
    }
    catch {
        Write-TrayLog "Failed to schedule background catalog refresh: $($_.Exception.Message)" -Level "WARN"
    }
}


function Initialize-ProfilesFromCliCatalog {
    <#
    .SYNOPSIS
    Loads profile metadata. Cache-first for snappy startup; CLI refresh
    runs in the background so the UI thread is never blocked.

    Order:
      1. Read on-disk cache (~10-50ms). If hit, use immediately and
         schedule a background CLI refresh that updates the cache for
         the NEXT tray start.
      2. If cache is empty (first install or corrupt), fall through to a
         blocking CLI call so the user has something to work with this
         session. Result is written to cache for subsequent fast starts.
      3. If both fail, keep built-in fallback profile defs.

    Also loads the retired-id alias map so tray-config favorites/defaults
    can be normalized on startup.

    Pre-2026-05-22 the tray ALWAYS blocked on CLI at startup, costing
    1.5-3s of cold-start latency on every tray relaunch (Python interpreter
    + import overhead per shell-out, x2 for the alias map). The cache
    contains identical data; using it directly drops that to ~50ms.
    #>
    $fallbackProfiles = if ($script:FallbackProfiles) {
        $script:FallbackProfiles
    }
    else {
        $script:Profiles
    }

    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $entries = @()
    $source = "fallback"
    $aliasMap = $null
    $script:ProfileCatalogLastSource = $null
    $script:ProfileCatalogLastCount = 0
    $script:ProfileCatalogUsedFallback = $false

    # Primary source: on-disk cache (snappy).
    $cachedEntries = Read-ProfileCatalogCacheEntries
    if ($cachedEntries.Count -gt 0) {
        $entries = @($cachedEntries)
        $aliasMap = Read-ProfileAliasMapFromCache
        $source = "cache"
        # Schedule a non-blocking refresh so the cache stays current.
        Start-BackgroundCatalogRefresh
    }

    # Cold fallback: cache is empty (first install or corrupted). Block on CLI
    # so the user has SOMETHING to work with this session. Subsequent starts
    # will hit the warm cache and skip this entirely.
    if ($entries.Count -eq 0 -and $script:PythonExe) {
        Write-TrayLog "Profile catalog cache miss; performing blocking CLI fetch (cold start)" -Level "INFO"
        $result = Invoke-CliCatalogRefresh
        $entries = if ($result.Entries) { @($result.Entries) } else { @() }
        $aliasMap = $result.AliasMap
        if ($entries.Count -gt 0) {
            $source = "cli (cold)"
            $null = Write-ProfileCatalogCache -Entries $entries -Aliases $aliasMap
        }
    }

    # Alias map: prefer whatever we already have, else read from cache.
    if (-not $aliasMap) {
        $aliasMap = Read-ProfileAliasMapFromCache
    }
    if (-not $aliasMap) { $aliasMap = @{} }
    $script:ProfileAliases = $aliasMap

    if ($entries.Count -gt 0) {
        $resolved = Convert-CatalogEntriesToProfileMap -Entries $entries -FallbackProfiles $fallbackProfiles
        if ($resolved.Count -gt 0) {
            $script:Profiles = $resolved
            $script:ProfileCatalogLastSource = $source
            $script:ProfileCatalogLastCount = $resolved.Count
            $script:ProfileCatalogUsedFallback = $false
            $sw.Stop()
            Write-TrayLog "Profile catalog loaded from $source ($($resolved.Count) profiles, $($script:ProfileAliases.Count) aliases) in $($sw.ElapsedMilliseconds)ms"
            return
        }

        Write-TrayLog "Resolved profile catalog from $source is empty; using built-in fallback definitions" -Level "WARN"
    }

    # Final source: built-in emergency fallback map in this script
    $script:Profiles = Copy-ProfileMap -Source $fallbackProfiles
    $script:ProfileCatalogLastSource = "built-in fallback"
    $script:ProfileCatalogLastCount = $script:Profiles.Count
    $script:ProfileCatalogUsedFallback = $true
    $sw.Stop()
    Write-TrayLog "Profile catalog using built-in fallback definitions ($($script:Profiles.Count) profiles, $($script:ProfileAliases.Count) aliases) in $($sw.ElapsedMilliseconds)ms" -Level "WARN"
}

Initialize-ProfilesFromCliCatalog

# Preferred order for known categories; any new ones sort alphabetically after
$preferredCategoryOrder = @("Desktop", "Fighting", "Shooters", "RPGs", "Other")
$allCategories = $script:Profiles.Values | ForEach-Object { $_.Cat } | Select-Object -Unique
$script:CategoryOrder = @()
foreach ($cat in $preferredCategoryOrder) {
    if ($allCategories -contains $cat) { $script:CategoryOrder += $cat }
}
foreach ($cat in ($allCategories | Sort-Object)) {
    if ($script:CategoryOrder -notcontains $cat) { $script:CategoryOrder += $cat }
}
$script:CategoryColors = @{
    "Desktop"      = $script:Colors.CategoryDesktop
    "Productivity" = $script:Colors.CategoryDesktop
    "Fighting"     = $script:Colors.CategoryFighting
    "RPGs"         = $script:Colors.CategoryRpg
    "ARPG"         = $script:Colors.CategoryRpg
    "Shooters"     = $script:Colors.CategoryShooter
    "Shooter"      = $script:Colors.CategoryShooter
    "Streaming"    = $script:Colors.CategoryDesktop
    "Other"        = $script:Colors.CategoryOther
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

function Get-TraySectionHeaderTint {
    param([string]$Section)

    switch -Regex ($Section) {
        "^Favorites$" { return (Blend-Color -Base $script:Colors.FavoriteStar -Overlay $script:Colors.Text -Ratio 0.42) }
        "^Recent$" { return (Blend-Color -Base $script:Colors.AccentBlue -Overlay $script:Colors.Text -Ratio 0.36) }
        "^Profiles$" { return (Blend-Color -Base $script:Colors.AccentGold -Overlay $script:Colors.Text -Ratio 0.30) }
        default { return $script:Colors.TextDim }
    }
}

function Get-TrayCategoryHeaderTint {
    param(
        [string]$Category,
        [System.Drawing.Color]$CategoryColor
    )

    $baseColor = if ($CategoryColor) { $CategoryColor } else { Get-CategoryColor -Category $Category -Fallback $script:Colors.TextDim }
    return (Blend-Color -Base $baseColor -Overlay $script:Colors.Text -Ratio 0.28)
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
    // Penumbra palette - editorial tech, deep ink with a single lagoon accent.
    private static readonly Color BgColor = Color.FromArgb(255, 7, 24, 29);   // ink-100
    private static readonly Color BgDark = Color.FromArgb(255, 4, 15, 18);     // ink-000
    private static readonly Color BgSubtle = Color.FromArgb(255, 11, 35, 42);  // ink-200
    private static readonly Color SepColor = Color.FromArgb(255, 12, 44, 49);  // rule-soft
    private static readonly Color BorderColor = Color.FromArgb(255, 26, 88, 90); // rule-strong
    private static readonly Color AccentGold = Color.FromArgb(255, 0, 245, 212);  // phosphor cyan (key name kept for diff hygiene)
    private static readonly Color AccentGoldDim = Color.FromArgb(60, 0, 245, 212);
    private static readonly Color TextPaper = Color.FromArgb(255, 225, 244, 240);
    private static readonly Color TextMist = Color.FromArgb(255, 148, 183, 182);
    public static int PulseFrame = 0;
    private const int SafeMenuMaxWidth = 520;

    public DarkThemeRenderer() : base(new DarkColorTable()) { }

    private static int GetSafeItemWidth(ToolStripItem item)
    {
        int width = 0;
        if (item != null)
        {
            width = item.Width;
            if (item.Owner != null)
            {
                int ownerWidth = item.Owner.ClientSize.Width;
                if (ownerWidth <= 0) ownerWidth = item.Owner.Width;
                if (ownerWidth > 0) width = width > 0 ? Math.Min(width, ownerWidth) : ownerWidth;
            }
        }
        if (width <= 0) width = SafeMenuMaxWidth;
        return Math.Max(1, Math.Min(SafeMenuMaxWidth, width));
    }

    private static Rectangle GetSafeItemRect(ToolStripItem item, int insetX, int insetY)
    {
        int width = GetSafeItemWidth(item);
        int height = item != null ? item.Height : 0;
        return new Rectangle(insetX, insetY, Math.Max(1, width - (insetX * 2)), Math.Max(1, height - (insetY * 2)));
    }

    private static Rectangle GetBoundedRowRect(Rectangle rect, int maxWidth, int minWidth)
    {
        int boundedWidth = Math.Min(rect.Width, Math.Max(1, maxWidth));
        boundedWidth = Math.Max(Math.Min(rect.Width, Math.Max(1, minWidth)), boundedWidth);
        return new Rectangle(rect.X, rect.Y, Math.Max(1, boundedWidth), rect.Height);
    }

    private static int GetSafeChipRight(ToolStripItem item)
    {
        return Math.Max(48, GetSafeItemWidth(item) - 24);
    }

    private static Color MixColor(Color baseColor, Color overlay, double ratio)
    {
        ratio = Math.Max(0.0, Math.Min(1.0, ratio));
        int r = (int)Math.Round(baseColor.R * (1.0 - ratio) + overlay.R * ratio);
        int g = (int)Math.Round(baseColor.G * (1.0 - ratio) + overlay.G * ratio);
        int b = (int)Math.Round(baseColor.B * (1.0 - ratio) + overlay.B * ratio);
        return Color.FromArgb(255, Math.Max(0, Math.Min(255, r)), Math.Max(0, Math.Min(255, g)), Math.Max(0, Math.Min(255, b)));
    }

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
        int w = GetSafeItemWidth(e.Item);
        int h = e.Item.Height;
        if (w < 2 || h < 2) return; // guard against zero-size layout passes
        var rect = GetSafeItemRect(e.Item, 3, 1);

        try
        {
            // --- Hero Banner: active profile status item ---
            var tag = e.Item.Tag as string;
            if (tag == "__hero_banner__")
            {
                Color tint = e.Item.ForeColor;
                double heroWave = (Math.Sin(PulseFrame / 6.0) + 1.0) / 2.0;
                int heroGlowAlpha = 36 + (int)(heroWave * 28);
                int heroRingAlpha = 120 + (int)(heroWave * 70);
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

                Image heroImage = e.Item.Image;
                bool hasHeroImage = heroImage != null;
                if (hasHeroImage)
                {
                    int medallionSize = Math.Min(32, Math.Max(24, h - 14));
                    int medallionX = 12;
                    int medallionY = Math.Max(4, (h - medallionSize) / 2);
                    using (var glowBrush = new SolidBrush(Color.FromArgb(heroGlowAlpha, tint.R, tint.G, tint.B)))
                    {
                        g.FillEllipse(glowBrush, medallionX - 4, medallionY - 4, medallionSize + 8, medallionSize + 8);
                    }
                    using (var backingBrush = new LinearGradientBrush(
                        new Rectangle(medallionX, medallionY, medallionSize, medallionSize),
                        Color.FromArgb(215, 11, 35, 42),
                        Color.FromArgb(230, 5, 19, 23),
                        LinearGradientMode.ForwardDiagonal))
                    {
                        g.FillEllipse(backingBrush, medallionX, medallionY, medallionSize, medallionSize);
                    }
                    using (var ringPen = new Pen(Color.FromArgb(160, tint.R, tint.G, tint.B), 1.2f))
                    {
                        g.DrawEllipse(ringPen, medallionX, medallionY, medallionSize - 1, medallionSize - 1);
                    }
                    int orbitStart = (PulseFrame * 9) % 360;
                    using (var orbitPen = new Pen(Color.FromArgb(heroRingAlpha, tint.R, tint.G, tint.B), 1.45f))
                    {
                        orbitPen.StartCap = LineCap.Round;
                        orbitPen.EndCap = LineCap.Round;
                        g.DrawArc(orbitPen, medallionX - 2, medallionY - 2, medallionSize + 3, medallionSize + 3, orbitStart, 82);
                    }
                    int imageSize = Math.Max(16, medallionSize - 10);
                    var imageRect = new Rectangle(
                        medallionX + ((medallionSize - imageSize) / 2),
                        medallionY + ((medallionSize - imageSize) / 2),
                        imageSize,
                        imageSize);
                    g.DrawImage(heroImage, imageRect);
                    int sweepX = medallionX + medallionSize + 8 + ((PulseFrame * 6) % Math.Max(1, w - medallionX - medallionSize - 88));
                    using (var sweepPen = new Pen(Color.FromArgb(32 + (int)(heroWave * 42), tint.R, tint.G, tint.B), 1.1f))
                    {
                        sweepPen.StartCap = LineCap.Round;
                        sweepPen.EndCap = LineCap.Round;
                        g.DrawLine(sweepPen, sweepX, 6, Math.Min(w - 18, sweepX + 48), 6);
                    }
                }
                else
                {
                    // Fallback glowing dot (10px circle with outer glow ring)
                    int dotX = 12;
                    int dotY = (h / 2) - 5;
                    using (var glowBrush = new SolidBrush(Color.FromArgb(heroGlowAlpha, tint.R, tint.G, tint.B)))
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
                }

                // Render text manually (profile name + subtitle)
                string text = e.Item.Text ?? "";
                string[] parts = text.Split('|');
                string name = parts.Length > 0 ? parts[0].Trim() : "";
                string subtitle = parts.Length > 1 ? parts[1].Trim() : "";

                g.TextRenderingHint = System.Drawing.Text.TextRenderingHint.ClearTypeGridFit;

                int textX = hasHeroImage ? 54 : 28;
                // Profile name: same Windows UI face as every tray label.
                Color brightTint = Color.FromArgb(255,
                    Math.Min(255, tint.R + 40),
                    Math.Min(255, tint.G + 40),
                    Math.Min(255, tint.B + 40));
                Font heroFont = ResolveHeroFont(13.0f, FontStyle.Regular);
                using (heroFont)
                using (var brush = new SolidBrush(brightTint))
                {
                    g.DrawString(name, heroFont, brush, textX, 4);
                }

                // Subtitle: same UI face, scaled down for hierarchy.
                if (!string.IsNullOrEmpty(subtitle))
                {
                    Color dimTint = Color.FromArgb(180, tint.R, tint.G, tint.B);
                    Font eyebrowFont = ResolveEyebrowFont(8.3f);
                    using (eyebrowFont)
                    using (var brush = new SolidBrush(dimTint))
                    {
                        g.DrawString(subtitle.ToUpperInvariant(), eyebrowFont, brush, textX, 28);
                    }
                }
                return;
            }

            // --- Status lane: compact truth chips for the durable tray footer ---
            if (e.Item.AccessibleName == "__status_bar__")
            {
                string chipRaw = e.Item.AccessibleDescription ?? "";
                Color tint = e.Item.ForeColor;
                if (chipRaw.Contains("FIX") || chipRaw.Contains("RESTART"))
                {
                    tint = Color.FromArgb(255, 245, 184, 64);
                }
                else if (chipRaw.Contains("CHECK") || chipRaw.Contains("PREVIEW"))
                {
                    tint = Color.FromArgb(255, 82, 199, 244);
                }
                else if (chipRaw.Contains("BACKUP"))
                {
                    tint = Color.FromArgb(255, 196, 137, 255);
                }
                else if (chipRaw.Contains("MIXED"))
                {
                    tint = Color.FromArgb(255, 245, 184, 64);
                }
                else if (chipRaw.Contains("DISPLAY") || chipRaw.Contains("GPU") || chipRaw.Contains("HZ"))
                {
                    tint = Color.FromArgb(255, 82, 199, 244);
                }
                else if (chipRaw.Contains("NO-DATA"))
                {
                    tint = Color.FromArgb(255, 95, 127, 127);
                }

                double statusWave = (Math.Sin(PulseFrame / 5.5) + 1.0) / 2.0;
                int fillAlpha = 14 + (int)(statusWave * 10);
                int edgeAlpha = 28 + (int)(statusWave * 28);
                if (rect.Width > 0 && rect.Height > 0)
                {
                    using (var brush = new LinearGradientBrush(
                        rect,
                        Color.FromArgb(fillAlpha, tint.R, tint.G, tint.B),
                        Color.FromArgb(5, tint.R, tint.G, tint.B),
                        LinearGradientMode.Horizontal))
                    {
                        FillRoundRect(g, brush, rect, 4);
                    }
                    using (var pen = new Pen(Color.FromArgb(edgeAlpha, tint.R, tint.G, tint.B), 1f))
                    {
                        DrawRoundRect(g, pen, rect, 4);
                    }

                    int railX = rect.X + 5;
                    int railH = Math.Max(4, rect.Height - 9);
                    using (var railBrush = new LinearGradientBrush(
                        new Rectangle(railX, rect.Y + 4, 3, railH),
                        Color.FromArgb(45, tint.R, tint.G, tint.B),
                        Color.FromArgb(170, tint.R, tint.G, tint.B),
                        LinearGradientMode.Vertical))
                    {
                        FillRoundRect(g, railBrush, new Rectangle(railX, rect.Y + 4, 3, railH), 1);
                    }

                    int sweepWidth = Math.Max(34, Math.Min(76, rect.Width / 3));
                    int sweepTravel = Math.Max(1, rect.Width - sweepWidth - 20);
                    int sweepX = rect.X + 12 + ((PulseFrame * 5) % sweepTravel);
                    using (var sweepPen = new Pen(Color.FromArgb(32 + (int)(statusWave * 36), tint.R, tint.G, tint.B), 1.0f))
                    {
                        sweepPen.StartCap = LineCap.Round;
                        sweepPen.EndCap = LineCap.Round;
                        g.DrawLine(sweepPen, sweepX, rect.Y + 2, Math.Min(rect.Right - 9, sweepX + sweepWidth), rect.Y + 2);
                    }
                }
                return;
            }

            // --- Top-level flyout commands: compact animated launcher pills ---
            if (e.Item.AccessibleName == "__flyout_command__")
            {
                Color tint = e.Item.ForeColor;
                double wave = (Math.Sin(PulseFrame / 5.0) + 1.0) / 2.0;
                int fillAlpha = 22 + (int)(wave * 12);
                int edgeAlpha = 42 + (int)(wave * 38);

                if (rect.Width > 0 && rect.Height > 0)
                {
                    using (var brush = new LinearGradientBrush(
                        rect,
                        Color.FromArgb(fillAlpha, tint.R, tint.G, tint.B),
                        Color.FromArgb(8, tint.R, tint.G, tint.B),
                        LinearGradientMode.Horizontal))
                    {
                        FillRoundRect(g, brush, rect, 5);
                    }
                    using (var pen = new Pen(Color.FromArgb(edgeAlpha, tint.R, tint.G, tint.B), 1f))
                    {
                        DrawRoundRect(g, pen, rect, 5);
                    }

                    int railX = rect.X + 5;
                    int railY = rect.Y + 5;
                    int railH = Math.Max(4, rect.Height - 10);
                    using (var railBrush = new LinearGradientBrush(
                        new Rectangle(railX, railY, 3, railH),
                        Color.FromArgb(60, tint.R, tint.G, tint.B),
                        Color.FromArgb(210, tint.R, tint.G, tint.B),
                        LinearGradientMode.Vertical))
                    {
                        FillRoundRect(g, railBrush, new Rectangle(railX, railY, 3, railH), 1);
                    }

                    int sweepWidth = Math.Max(34, Math.Min(70, rect.Width / 3));
                    int sweepTravel = Math.Max(1, rect.Width - sweepWidth - 24);
                    int sweepX = rect.X + 14 + ((PulseFrame * 5) % sweepTravel);
                    using (var sweepPen = new Pen(Color.FromArgb(44 + (int)(wave * 44), tint.R, tint.G, tint.B), 1.0f))
                    {
                        g.DrawLine(sweepPen, sweepX, rect.Y + 2, Math.Min(rect.Right - 10, sweepX + sweepWidth), rect.Y + 2);
                    }
                }

                using (var brush = new SolidBrush(Color.FromArgb(18 + (int)(wave * 14), tint.R, tint.G, tint.B)))
                {
                    g.FillEllipse(brush, 2, rect.Y - 2, 28, rect.Height + 4);
                }
            }

            // --- Game group rows: readable lane entries with color carried by rails/icons ---
            if (e.Item.AccessibleName == "__game_group_row__")
            {
                Color tint = e.Item.ForeColor;
                Rectangle laneRect = GetBoundedRowRect(rect, 350, 190);
                if (laneRect.Width > 0 && laneRect.Height > 0)
                {
                    using (var brush = new LinearGradientBrush(
                        laneRect,
                        Color.FromArgb(20, tint.R, tint.G, tint.B),
                        Color.FromArgb(4, tint.R, tint.G, tint.B),
                        LinearGradientMode.Horizontal))
                    {
                        FillRoundRect(g, brush, laneRect, 4);
                    }

                    var railRect = new Rectangle(laneRect.X + 5, laneRect.Y + 4, 4, Math.Max(3, laneRect.Height - 8));
                    using (var railBrush = new LinearGradientBrush(
                        railRect,
                        Color.FromArgb(70, tint.R, tint.G, tint.B),
                        Color.FromArgb(220, tint.R, tint.G, tint.B),
                        LinearGradientMode.Vertical))
                    {
                        FillRoundRect(g, railBrush, railRect, 2);
                    }

                    using (var pen = new Pen(Color.FromArgb(64, tint.R, tint.G, tint.B), 1f))
                    {
                        g.DrawLine(pen, laneRect.X + 18, laneRect.Y + 1, Math.Min(laneRect.Right - 14, laneRect.X + 128), laneRect.Y + 1);
                    }
                }
            }

            // --- Section headers: disabled + bold items (section/category bands) ---
            if (!e.Item.Enabled && e.Item.Font != null && e.Item.Font.Bold)
            {
                Color tint = e.Item.ForeColor;
                bool isSectionHeader = e.Item.AccessibleName == "__section_header__";
                bool isCategoryHeader = e.Item.AccessibleName == "__category_header__";
                int fillAlpha = isCategoryHeader ? 18 : 14;
                int lineAlpha = isCategoryHeader ? 90 : 72;

                // Header bands use color as structure; selectable rows use color as text.
                using (var brush = new LinearGradientBrush(
                    new Rectangle(0, 0, Math.Max(1, w), Math.Max(1, h)),
                    Color.FromArgb(fillAlpha, tint.R, tint.G, tint.B),
                    Color.FromArgb(isCategoryHeader ? 3 : 1, tint.R, tint.G, tint.B),
                    LinearGradientMode.Horizontal))
                {
                    g.FillRectangle(brush, 0, 0, w, h);
                }

                var railRect = new Rectangle(5, 4, isCategoryHeader ? 5 : 6, Math.Max(2, h - 8));
                using (var railBrush = new LinearGradientBrush(
                    railRect,
                    Color.FromArgb(isCategoryHeader ? 205 : 150, tint.R, tint.G, tint.B),
                    Color.FromArgb(isCategoryHeader ? 78 : 46, tint.R, tint.G, tint.B),
                    LinearGradientMode.Vertical))
                {
                    FillRoundRect(g, railBrush, railRect, 2);
                }

                using (var pen = new Pen(Color.FromArgb(lineAlpha, tint.R, tint.G, tint.B), 1f))
                {
                    int lineY = h - 1;
                    g.DrawLine(pen, 18, lineY, Math.Min(w - 10, 380), lineY);
                }

                if (isCategoryHeader && w > 90)
                {
                    using (var railPen = new Pen(Color.FromArgb(150, tint.R, tint.G, tint.B), 1.2f))
                    {
                        railPen.StartCap = LineCap.Round;
                        railPen.EndCap = LineCap.Round;
                        g.DrawLine(railPen, 22, 3, Math.Min(w - 18, 118), 3);
                    }
                }
                else if (isSectionHeader && w > 120)
                {
                    Color labelGlow = MixColor(tint, Color.White, 0.45);
                    using (var railPen = new Pen(Color.FromArgb(94, labelGlow.R, labelGlow.G, labelGlow.B), 1.15f))
                    {
                        railPen.StartCap = LineCap.Round;
                        railPen.EndCap = LineCap.Round;
                        g.DrawLine(railPen, 22, 3, Math.Min(w - 18, 150), 3);
                    }
                }
                return;
            }

            var profileMenuItem = e.Item as ToolStripMenuItem;
            bool isActiveProfileRow = e.Item.AccessibleName == "__profile_menu_item__" &&
                profileMenuItem != null && profileMenuItem.Checked;
            if (isActiveProfileRow)
            {
                Color tint = e.Item.ForeColor;
                double wave = (Math.Sin(PulseFrame / 4.0) + 1.0) / 2.0;
                int fillAlpha = 24 + (int)(wave * 18);
                int ringAlpha = 52 + (int)(wave * 58);
                Rectangle activeRect = GetBoundedRowRect(rect, 430, 250);

                if (activeRect.Width > 0 && activeRect.Height > 0)
                {
                    using (var brush = new LinearGradientBrush(
                        activeRect,
                        Color.FromArgb(fillAlpha, tint.R, tint.G, tint.B),
                        Color.FromArgb(10, tint.R, tint.G, tint.B),
                        LinearGradientMode.Horizontal))
                    {
                        FillRoundRect(g, brush, activeRect, 5);
                    }
                    using (var pen = new Pen(Color.FromArgb(ringAlpha, tint.R, tint.G, tint.B), 1f))
                    {
                        DrawRoundRect(g, pen, activeRect, 5);
                    }

                    int sweepWidth = Math.Max(36, Math.Min(84, activeRect.Width / 3));
                    int sweepTravel = Math.Max(1, activeRect.Width - sweepWidth - 18);
                    int sweepX = activeRect.X + 9 + ((PulseFrame * 7) % sweepTravel);
                    using (var sweepPen = new Pen(Color.FromArgb(80 + (int)(wave * 85), tint.R, tint.G, tint.B), 1.25f))
                    {
                        g.DrawLine(sweepPen, sweepX, activeRect.Y + 2, Math.Min(activeRect.Right - 9, sweepX + sweepWidth), activeRect.Y + 2);
                    }
                }

                using (var brush = new SolidBrush(Color.FromArgb(30 + (int)(wave * 25), tint.R, tint.G, tint.B)))
                {
                    g.FillEllipse(brush, 2, rect.Y - 2, 28, rect.Height + 4);
                }
            }

            if (e.Item.Selected && e.Item.Enabled)
            {
                Color tint = e.Item.ForeColor;
                Rectangle selectedRect = GetBoundedRowRect(rect, 440, 250);

                if (selectedRect.Width > 0 && selectedRect.Height > 0)
                {
                    // Gradient fill: category-tinted with subtle horizontal gradient
                    using (var brush = new LinearGradientBrush(
                        selectedRect, Color.FromArgb(35, tint.R, tint.G, tint.B),
                        Color.FromArgb(12, tint.R, tint.G, tint.B),
                        LinearGradientMode.Horizontal))
                    {
                        FillRoundRect(g, brush, selectedRect, 5);
                    }

                    // Subtle border
                    using (var pen = new Pen(Color.FromArgb(40, tint.R, tint.G, tint.B), 1f))
                    {
                        DrawRoundRect(g, pen, selectedRect, 5);
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
                var fadeRect = new Rectangle(selectedRect.Right - fadeW, selectedRect.Y, fadeW, selectedRect.Height);
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
            int w = GetSafeItemWidth(e.Item);
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

        if (e.Item.AccessibleName == "__status_bar__")
        {
            try
            {
                Rectangle textRect = e.TextRectangle;
                string label = (e.Item.Text ?? "").Trim();
                string chipRaw = e.Item.AccessibleDescription ?? "";
                string[] chips = chipRaw.Split(new char[] { '|' }, StringSplitOptions.RemoveEmptyEntries);
                int chipRight = GetSafeChipRight(e.Item);

                using (var chipFont = ResolveEyebrowFont(7.0f))
                using (var chipTextBrush = new SolidBrush(Color.FromArgb(226, 228, 246, 242)))
                using (var chipFormat = new StringFormat())
                {
                    chipFormat.Alignment = StringAlignment.Center;
                    chipFormat.LineAlignment = StringAlignment.Center;
                    chipFormat.Trimming = StringTrimming.EllipsisCharacter;
                    chipFormat.FormatFlags = StringFormatFlags.NoWrap;

                    for (int i = chips.Length - 1; i >= 0; i--)
                    {
                        string chip = chips[i].Trim();
                        if (string.IsNullOrWhiteSpace(chip)) continue;
                        SizeF chipSize = e.Graphics.MeasureString(chip, chipFont);
                        int chipWidth = Math.Max(34, Math.Min(66, (int)Math.Ceiling(chipSize.Width) + 12));
                        int chipX = chipRight - chipWidth;
                        if (chipX <= textRect.X + 82) continue;

                        Rectangle chipRect = new Rectangle(chipX, Math.Max(3, (e.Item.Height - 15) / 2), chipWidth, 15);
                        Color tint = e.Item.ForeColor;
                        if (chip == "FIX" || chip == "RESTART")
                        {
                            tint = Color.FromArgb(255, 245, 184, 64);
                        }
                        else if (chip == "CHECK" || chip == "PREVIEW")
                        {
                            tint = Color.FromArgb(255, 82, 199, 244);
                        }
                        else if (chip == "BACKUP")
                        {
                            tint = Color.FromArgb(255, 196, 137, 255);
                        }
                        else if (chip == "MIXED")
                        {
                            tint = Color.FromArgb(255, 245, 184, 64);
                        }
                        else if (chip == "DISPLAY" || chip == "GPU" || chip == "HZ")
                        {
                            tint = Color.FromArgb(255, 82, 199, 244);
                        }
                        else if (chip == "NO-DATA")
                        {
                            tint = Color.FromArgb(255, 95, 127, 127);
                        }

                        using (var chipBrush = new LinearGradientBrush(
                            chipRect,
                            Color.FromArgb(50, tint.R, tint.G, tint.B),
                            Color.FromArgb(15, tint.R, tint.G, tint.B),
                            LinearGradientMode.Horizontal))
                        {
                            FillRoundRect(e.Graphics, chipBrush, chipRect, 4);
                        }
                        using (var chipPen = new Pen(Color.FromArgb(82, tint.R, tint.G, tint.B), 1f))
                        {
                            DrawRoundRect(e.Graphics, chipPen, chipRect, 4);
                        }
                        e.Graphics.DrawString(chip, chipFont, chipTextBrush, chipRect, chipFormat);
                        chipRight = chipX - 4;
                    }
                }

                Rectangle labelRect = new Rectangle(
                    textRect.X,
                    textRect.Y,
                    Math.Max(24, chipRight - textRect.X - 8),
                    textRect.Height);
                using (var format = new StringFormat())
                using (var brush = new SolidBrush(Color.FromArgb(206, e.Item.ForeColor.R, e.Item.ForeColor.G, e.Item.ForeColor.B)))
                {
                    format.Trimming = StringTrimming.EllipsisCharacter;
                    format.FormatFlags = StringFormatFlags.NoWrap;
                    format.LineAlignment = StringAlignment.Center;
                    e.Graphics.TextRenderingHint = System.Drawing.Text.TextRenderingHint.ClearTypeGridFit;
                    e.Graphics.DrawString(label, e.TextFont, brush, labelRect, format);
                }
                return;
            }
            catch {}
        }

        if (e.Item.AccessibleName == "__flyout_command__")
        {
            try
            {
                Rectangle textRect = e.TextRectangle;
                int chipRight = GetSafeChipRight(e.Item);
                string chip = (e.Item.AccessibleDescription ?? "").Trim();
                bool hasChip = !string.IsNullOrWhiteSpace(chip);
                Rectangle chipRect = Rectangle.Empty;

                if (hasChip)
                {
                    using (var chipMeasureFont = ResolveEyebrowFont(7.4f))
                    {
                        SizeF chipSize = e.Graphics.MeasureString(chip, chipMeasureFont);
                        int chipWidth = Math.Max(42, Math.Min(88, (int)Math.Ceiling(chipSize.Width) + 12));
                        int chipX = chipRight - chipWidth;
                        if (chipX > textRect.X + 68)
                        {
                            chipRect = new Rectangle(chipX, Math.Max(3, (e.Item.Height - 15) / 2), chipWidth, 15);
                        }
                    }
                }

                Rectangle labelRect = chipRect.IsEmpty
                    ? textRect
                    : new Rectangle(textRect.X, textRect.Y, Math.Max(18, chipRect.X - textRect.X - 8), textRect.Height);
                using (var labelFormat = new StringFormat())
                using (var labelBrush = new SolidBrush(e.Item.ForeColor))
                using (var labelFont = ResolveEyebrowFont(9.6f))
                {
                    labelFormat.Trimming = StringTrimming.EllipsisCharacter;
                    labelFormat.FormatFlags = StringFormatFlags.NoWrap;
                    labelFormat.LineAlignment = StringAlignment.Center;
                    e.Graphics.TextRenderingHint = System.Drawing.Text.TextRenderingHint.ClearTypeGridFit;
                    e.Graphics.DrawString((e.Text ?? "").Trim().ToUpperInvariant(), labelFont, labelBrush, labelRect, labelFormat);
                }

                if (!chipRect.IsEmpty)
                {
                    Color tint = e.Item.ForeColor;
                    using (var chipBrush = new LinearGradientBrush(
                        chipRect,
                        Color.FromArgb(58, tint.R, tint.G, tint.B),
                        Color.FromArgb(18, tint.R, tint.G, tint.B),
                        LinearGradientMode.Horizontal))
                    {
                        FillRoundRect(e.Graphics, chipBrush, chipRect, 4);
                    }
                    using (var chipPen = new Pen(Color.FromArgb(84, tint.R, tint.G, tint.B), 1f))
                    {
                        DrawRoundRect(e.Graphics, chipPen, chipRect, 4);
                    }
                    using (var chipFont = ResolveEyebrowFont(7.4f))
                    using (var chipTextBrush = new SolidBrush(Color.FromArgb(228, 228, 246, 242)))
                    using (var chipFormat = new StringFormat())
                    {
                        chipFormat.Alignment = StringAlignment.Center;
                        chipFormat.LineAlignment = StringAlignment.Center;
                        chipFormat.Trimming = StringTrimming.EllipsisCharacter;
                        chipFormat.FormatFlags = StringFormatFlags.NoWrap;
                        e.Graphics.DrawString(chip.ToUpperInvariant(), chipFont, chipTextBrush, chipRect, chipFormat);
                    }
                }
                return;
            }
            catch {}
        }

        if (e.Item.AccessibleName == "__game_group_row__")
        {
            try
            {
                Rectangle textRect = e.TextRectangle;
                Color labelColor = TextPaper;
                Rectangle labelRect = new Rectangle(textRect.X, textRect.Y, Math.Max(18, textRect.Width - 8), textRect.Height);
                using (var labelFormat = new StringFormat())
                using (var labelBrush = new SolidBrush(labelColor))
                {
                    labelFormat.Trimming = StringTrimming.EllipsisCharacter;
                    labelFormat.FormatFlags = StringFormatFlags.NoWrap;
                    labelFormat.LineAlignment = StringAlignment.Center;
                    e.Graphics.TextRenderingHint = System.Drawing.Text.TextRenderingHint.ClearTypeGridFit;
                    e.Graphics.DrawString((e.Text ?? "").Trim(), e.TextFont, labelBrush, labelRect, labelFormat);
                }
                return;
            }
            catch {}
        }

        if (e.Item.AccessibleName == "__category_header__" || e.Item.AccessibleName == "__section_header__")
        {
            try
            {
                Rectangle textRect = e.TextRectangle;
                int chipRight = GetSafeChipRight(e.Item);
                string chipRaw = e.Item.AccessibleDescription ?? "";
                string[] chips = chipRaw.Split(new char[] { '|' }, StringSplitOptions.RemoveEmptyEntries);
                bool isSectionHeader = e.Item.AccessibleName == "__section_header__";
                bool isCategoryHeader = e.Item.AccessibleName == "__category_header__";
                // Hierarchy pyramid: hero (13) > game rows (11.25) > category
                // eyebrows (10.8, accent-tinted) > section eyebrows (9.8, dim).
                // Wayfinding labels must never out-shout the content rows.
                float labelSize = isSectionHeader ? 9.8f : 10.8f;
                int labelAlpha = isSectionHeader ? 232 : 255;
                Color labelColor = isCategoryHeader
                    ? MixColor(e.Item.ForeColor, TextPaper, 0.35)
                    : MixColor(TextMist, e.Item.ForeColor, 0.30);

                using (var chipFont = ResolveEyebrowFont(6.6f))
                using (var chipTextBrush = new SolidBrush(Color.FromArgb(225, 228, 246, 242)))
                using (var chipFormat = new StringFormat())
                {
                    chipFormat.Alignment = StringAlignment.Center;
                    chipFormat.LineAlignment = StringAlignment.Center;
                    chipFormat.Trimming = StringTrimming.EllipsisCharacter;
                    chipFormat.FormatFlags = StringFormatFlags.NoWrap;

                    for (int i = chips.Length - 1; i >= 0; i--)
                    {
                        string chip = chips[i].Trim();
                        if (string.IsNullOrWhiteSpace(chip)) continue;
                        SizeF chipSize = e.Graphics.MeasureString(chip, chipFont);
                        int chipWidth = Math.Max(38, Math.Min(72, (int)Math.Ceiling(chipSize.Width) + 12));
                        int chipX = chipRight - chipWidth;
                        if (chipX <= textRect.X + 68) continue;

                        Rectangle chipRect = new Rectangle(chipX, Math.Max(3, (e.Item.Height - 15) / 2), chipWidth, 15);
                        Color tint = e.Item.ForeColor;
                        using (var chipBrush = new LinearGradientBrush(
                            chipRect,
                            Color.FromArgb(46, tint.R, tint.G, tint.B),
                            Color.FromArgb(14, tint.R, tint.G, tint.B),
                            LinearGradientMode.Horizontal))
                        {
                            FillRoundRect(e.Graphics, chipBrush, chipRect, 4);
                        }
                        using (var chipPen = new Pen(Color.FromArgb(72, tint.R, tint.G, tint.B), 1f))
                        {
                            DrawRoundRect(e.Graphics, chipPen, chipRect, 4);
                        }
                        e.Graphics.DrawString(chip, chipFont, chipTextBrush, chipRect, chipFormat);
                        chipRight = chipX - 4;
                    }
                }

                Rectangle labelRect = new Rectangle(
                    textRect.X,
                    textRect.Y,
                    Math.Max(22, chipRight - textRect.X - 8),
                    textRect.Height);
                using (var labelFormat = new StringFormat())
                using (var labelFont = ResolveEyebrowFont(labelSize))
                using (var labelBrush = new SolidBrush(Color.FromArgb(labelAlpha, labelColor.R, labelColor.G, labelColor.B)))
                {
                    labelFormat.Trimming = StringTrimming.EllipsisCharacter;
                    labelFormat.FormatFlags = StringFormatFlags.NoWrap;
                    labelFormat.LineAlignment = StringAlignment.Center;
                    e.Graphics.TextRenderingHint = System.Drawing.Text.TextRenderingHint.ClearTypeGridFit;
                    e.Graphics.DrawString((e.Item.Text ?? "").Trim().ToUpperInvariant(), labelFont, labelBrush, labelRect, labelFormat);
                }
                return;
            }
            catch {}
        }

        if (e.Item.AccessibleName == "__game_flyout_header__")
        {
            try
            {
                string rawText = e.Item.Text ?? "";
                string[] parts = rawText.Split('|');
                string labelText = parts.Length > 0 ? parts[0].Trim() : rawText.Trim();
                if (parts.Length > 1 && !string.IsNullOrWhiteSpace(parts[1]))
                {
                    labelText = labelText + "  |  " + parts[1].Trim();
                }

                Rectangle textRect = e.TextRectangle;
                int chipRight = GetSafeChipRight(e.Item);
                string chipRaw = e.Item.AccessibleDescription ?? "";
                string[] chips = chipRaw.Split(new char[] { '|' }, StringSplitOptions.RemoveEmptyEntries);

                using (var chipFont = ResolveEyebrowFont(7.0f))
                using (var chipTextBrush = new SolidBrush(Color.FromArgb(230, 228, 246, 242)))
                using (var chipFormat = new StringFormat())
                {
                    chipFormat.Alignment = StringAlignment.Center;
                    chipFormat.LineAlignment = StringAlignment.Center;
                    chipFormat.Trimming = StringTrimming.EllipsisCharacter;
                    chipFormat.FormatFlags = StringFormatFlags.NoWrap;

                    for (int i = chips.Length - 1; i >= 0; i--)
                    {
                        string chip = chips[i].Trim();
                        if (string.IsNullOrWhiteSpace(chip)) continue;
                        SizeF chipSize = e.Graphics.MeasureString(chip, chipFont);
                        int chipWidth = Math.Max(36, Math.Min(76, (int)Math.Ceiling(chipSize.Width) + 12));
                        int chipX = chipRight - chipWidth;
                        if (chipX <= textRect.X + 86) continue;

                        Rectangle chipRect = new Rectangle(chipX, Math.Max(3, (e.Item.Height - 15) / 2), chipWidth, 15);
                        Color tint = e.Item.ForeColor;
                        using (var chipBrush = new LinearGradientBrush(
                            chipRect,
                            Color.FromArgb(50, tint.R, tint.G, tint.B),
                            Color.FromArgb(16, tint.R, tint.G, tint.B),
                            LinearGradientMode.Horizontal))
                        {
                            FillRoundRect(e.Graphics, chipBrush, chipRect, 4);
                        }
                        using (var chipPen = new Pen(Color.FromArgb(80, tint.R, tint.G, tint.B), 1f))
                        {
                            DrawRoundRect(e.Graphics, chipPen, chipRect, 4);
                        }
                        e.Graphics.DrawString(chip, chipFont, chipTextBrush, chipRect, chipFormat);
                        chipRight = chipX - 4;
                    }
                }

                Rectangle labelRect = new Rectangle(
                    textRect.X,
                    textRect.Y,
                    Math.Max(22, chipRight - textRect.X - 8),
                    textRect.Height);
                using (var labelFormat = new StringFormat())
                using (var labelFont = ResolveEyebrowFont(8.4f))
                using (var labelBrush = new SolidBrush(e.Item.ForeColor))
                {
                    labelFormat.Trimming = StringTrimming.EllipsisCharacter;
                    labelFormat.FormatFlags = StringFormatFlags.NoWrap;
                    labelFormat.LineAlignment = StringAlignment.Center;
                    e.Graphics.TextRenderingHint = System.Drawing.Text.TextRenderingHint.ClearTypeGridFit;
                    e.Graphics.DrawString(labelText.ToUpperInvariant(), labelFont, labelBrush, labelRect, labelFormat);
                }
                return;
            }
            catch {}
        }

        if (e.Item.AccessibleName == "__profile_menu_item__" || e.Item.AccessibleName == "__backup_menu_item__")
        {
            try
            {
                string chipRaw = e.Item.AccessibleDescription ?? "";
                string[] chips = chipRaw.Split(new char[] { '|' }, StringSplitOptions.RemoveEmptyEntries);
                bool hasChip = chips.Length > 0;
                Rectangle textRect = e.TextRectangle;
                int chipRight = GetSafeChipRight(e.Item);
                if (hasChip)
                {
                    using (var chipMeasureFont = ResolveEyebrowFont(7.2f))
                    {
                        for (int i = chips.Length - 1; i >= 0; i--)
                        {
                            string chip = chips[i].Trim();
                            if (string.IsNullOrWhiteSpace(chip)) continue;
                            SizeF chipSize = e.Graphics.MeasureString(chip, chipMeasureFont);
                            int chipWidth = Math.Max(42, Math.Min(76, (int)Math.Ceiling(chipSize.Width) + 14));
                            int chipX = chipRight - chipWidth;
                            if (chipX <= textRect.X + 18) continue;
                            chipRight = chipX - 4;
                        }
                    }
                }

                Rectangle labelRect = hasChip
                    ? new Rectangle(textRect.X, textRect.Y, Math.Max(18, chipRight - textRect.X - 8), textRect.Height)
                    : textRect;
                using (var format = new StringFormat())
                {
                    format.Trimming = StringTrimming.EllipsisCharacter;
                    format.FormatFlags = StringFormatFlags.NoWrap;
                    format.LineAlignment = StringAlignment.Center;
                    Color rowTextColor = e.Item.AccessibleName == "__backup_menu_item__" ? TextMist : TextPaper;
                    using (var brush = new SolidBrush(rowTextColor))
                    {
                        e.Graphics.TextRenderingHint = System.Drawing.Text.TextRenderingHint.ClearTypeGridFit;
                        e.Graphics.DrawString(e.Text, e.TextFont, brush, labelRect, format);
                    }
                }

                if (hasChip)
                {
                    Color tint = e.Item.ForeColor;
                    var profileMenuItem = e.Item as ToolStripMenuItem;
                    bool isActiveProfileChip = profileMenuItem != null && profileMenuItem.Checked;
                    double chipWave = (Math.Sin(PulseFrame / 4.5) + 1.0) / 2.0;
                    int chipFillAlpha = isActiveProfileChip ? 72 + (int)(chipWave * 24) : 62;
                    int chipFadeAlpha = isActiveProfileChip ? 26 + (int)(chipWave * 16) : 22;
                    int chipEdgeAlpha = isActiveProfileChip ? 105 + (int)(chipWave * 70) : 90;
                    using (var chipFont = ResolveEyebrowFont(7.2f))
                    using (var chipTextBrush = new SolidBrush(Color.FromArgb(230, 228, 246, 242)))
                    using (var chipFormat = new StringFormat())
                    {
                        chipFormat.Alignment = StringAlignment.Center;
                        chipFormat.LineAlignment = StringAlignment.Center;
                        chipFormat.Trimming = StringTrimming.EllipsisCharacter;
                        chipFormat.FormatFlags = StringFormatFlags.NoWrap;
                        chipRight = GetSafeChipRight(e.Item);
                        for (int i = chips.Length - 1; i >= 0; i--)
                        {
                            string chip = chips[i].Trim();
                            if (string.IsNullOrWhiteSpace(chip)) continue;
                            SizeF chipSize = e.Graphics.MeasureString(chip, chipFont);
                            int chipWidth = Math.Max(42, Math.Min(76, (int)Math.Ceiling(chipSize.Width) + 14));
                            int chipX = chipRight - chipWidth;
                            if (chipX <= textRect.X + 18) continue;
                            Rectangle chipRect = new Rectangle(
                                chipX,
                                Math.Max(3, (e.Item.Height - 15) / 2),
                                chipWidth,
                                15);

                            using (var chipBrush = new LinearGradientBrush(
                                chipRect,
                                Color.FromArgb(chipFillAlpha, tint.R, tint.G, tint.B),
                                Color.FromArgb(chipFadeAlpha, tint.R, tint.G, tint.B),
                                LinearGradientMode.Horizontal))
                            {
                                FillRoundRect(e.Graphics, chipBrush, chipRect, 4);
                            }
                            using (var chipPen = new Pen(Color.FromArgb(chipEdgeAlpha, tint.R, tint.G, tint.B), 1f))
                            {
                                DrawRoundRect(e.Graphics, chipPen, chipRect, 4);
                            }
                            if (isActiveProfileChip && chipRect.Width > 26)
                            {
                                int sweepWidth = Math.Max(10, Math.Min(22, chipRect.Width / 2));
                                int sweepTravel = Math.Max(1, chipRect.Width - sweepWidth - 8);
                                int chipSweepX = chipRect.X + 4 + ((PulseFrame * 4) % sweepTravel);
                                using (var chipSweepPen = new Pen(Color.FromArgb(68 + (int)(chipWave * 54), 228, 246, 242), 1.0f))
                                {
                                    chipSweepPen.StartCap = LineCap.Round;
                                    chipSweepPen.EndCap = LineCap.Round;
                                    e.Graphics.DrawLine(chipSweepPen, chipSweepX, chipRect.Y + 2, Math.Min(chipRect.Right - 4, chipSweepX + sweepWidth), chipRect.Y + 2);
                                }
                            }
                            e.Graphics.DrawString(chip, chipFont, chipTextBrush, chipRect, chipFormat);
                            chipRight = chipX - 4;
                        }
                    }
                }
                return;
            }
            catch {}
        }

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

    // Tray typography uses the Windows UI face everywhere; size and weight
    // carry hierarchy instead of switching families between rows.
    // Segoe-only type system by design (see the static test pins that forbid
    // Bahnschrift/Cascadia/Consolas). The Variable optical families are
    // Win11-stock refinements of the same voice: Display tightens the hero,
    // Small keeps 7-10pt eyebrow caps open and legible. Both fall back to
    // classic Segoe UI on older builds.
    private static readonly string[] HeroFontStack = new[] {
        "Segoe UI Variable Display", "Segoe UI"
    };
    private static readonly string[] EyebrowFontStack = new[] {
        "Segoe UI Variable Small", "Segoe UI"
    };

    private static Font ResolveFontStack(string[] families, float size, FontStyle style)
    {
        foreach (var fam in families)
        {
            try
            {
                var f = new Font(fam, size, style);
                if (string.Equals(f.FontFamily.Name, fam, StringComparison.OrdinalIgnoreCase))
                    return f;
                string root = fam.Split(' ')[0];
                if (f.FontFamily.Name.StartsWith(root, StringComparison.OrdinalIgnoreCase))
                    return f;
                f.Dispose();
            }
            catch {}
        }
        return new Font("Segoe UI", size, style);
    }

    public static Font ResolveHeroFont(float size, FontStyle style)
    {
        return ResolveFontStack(HeroFontStack, size, style);
    }
    public static Font ResolveEyebrowFont(float size)
    {
        return ResolveFontStack(EyebrowFontStack, size, FontStyle.Bold);
    }
}

public class DarkColorTable : ProfessionalColorTable
{
    public override Color MenuBorder { get { return Color.FromArgb(255, 26, 88, 90); } }
    public override Color MenuItemBorder { get { return Color.Transparent; } }
    public override Color MenuItemSelected { get { return Color.FromArgb(255, 20, 66, 74); } }
    public override Color MenuItemSelectedGradientBegin { get { return Color.FromArgb(255, 13, 42, 50); } }
    public override Color MenuItemSelectedGradientEnd { get { return Color.FromArgb(255, 13, 42, 50); } }
    public override Color MenuItemPressedGradientBegin { get { return Color.FromArgb(255, 11, 35, 42); } }
    public override Color MenuItemPressedGradientEnd { get { return Color.FromArgb(255, 11, 35, 42); } }
    public override Color MenuStripGradientBegin { get { return Color.FromArgb(255, 7, 24, 29); } }
    public override Color MenuStripGradientEnd { get { return Color.FromArgb(255, 7, 24, 29); } }
    public override Color ToolStripDropDownBackground { get { return Color.FromArgb(255, 7, 24, 29); } }
    public override Color ImageMarginGradientBegin { get { return Color.FromArgb(255, 7, 24, 29); } }
    public override Color ImageMarginGradientMiddle { get { return Color.FromArgb(255, 7, 24, 29); } }
    public override Color ImageMarginGradientEnd { get { return Color.FromArgb(255, 7, 24, 29); } }
    public override Color SeparatorDark { get { return Color.FromArgb(255, 13, 42, 50); } }
    public override Color SeparatorLight { get { return Color.Transparent; } }
    public override Color CheckBackground { get { return Color.FromArgb(255, 13, 42, 50); } }
    public override Color CheckSelectedBackground { get { return Color.FromArgb(255, 16, 52, 60); } }
    public override Color CheckPressedBackground { get { return Color.FromArgb(255, 11, 35, 42); } }
}
"@ -ReferencedAssemblies System.Windows.Forms,System.Drawing -ErrorAction SilentlyContinue

# ============================================================================
# ICON STATE MANAGEMENT
# ============================================================================

# Cached shared fonts (disposed in finally block).
# Tray type system: Segoe UI everywhere, with scale/weight/color carrying
# hierarchy. The scale is a pyramid that keeps content above wayfinding:
#   hero 13.0 bold > game/menu rows 11.25 > category eyebrows 10.8 (accent
#   caps) > section eyebrows 9.8 (dim caps) > chips ~7 (caps).
# Section/category headers deliberately render SMALLER than the rows they
# label - the accent rail, tick, and rule carry the banding, so the label
# can stay quiet instead of shouting over the game names.
$script:FontNormal  = New-Object System.Drawing.Font("Segoe UI", 10.0)
$script:FontBold    = New-Object System.Drawing.Font("Segoe UI", 10.0, [System.Drawing.FontStyle]::Bold)
$script:FontEyebrow = [DarkThemeRenderer]::ResolveEyebrowFont(8.6)
$script:FontHero    = [DarkThemeRenderer]::ResolveHeroFont(13.0, [System.Drawing.FontStyle]::Bold)
$script:FontMenuRow = New-Object System.Drawing.Font("Segoe UI", 11.25)
$script:FontMenuRowBold = New-Object System.Drawing.Font("Segoe UI", 11.25, [System.Drawing.FontStyle]::Bold)
$script:FontSectionHeader = [DarkThemeRenderer]::ResolveEyebrowFont(9.8)
$script:FontCategoryHeader = [DarkThemeRenderer]::ResolveEyebrowFont(10.8)
$script:FontMono    = New-Object System.Drawing.Font("Segoe UI", 9.0)

$script:TrayMenuPreferredWidth = 520
$script:TrayMenuMinimumWidth = 360
$script:TrayMenuScreenMargin = 48
$script:IconState = "Idle"
$script:ApplyAnimTimer = $null
$script:TrayMenuPulseTimer = $null
$script:TrayMenuPulseFrame = 0
$script:StartupIconHealTimer = $null
$script:StartupIconHealAttempts = 0
$script:ProcessGuardTimer = $null
$script:MenuStateInitialized = $false
$script:LastRenderedActiveProfile = $null
$script:AboutForm = $null

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

function Set-MenuItemImageSafe {
    <#
    .SYNOPSIS
    Replaces a ToolStrip item's image and disposes the previous one.
    #>
    param(
        [System.Windows.Forms.ToolStripItem]$Item,
        [AllowNull()][System.Drawing.Image]$NewImage
    )

    if (-not $Item) {
        if ($NewImage) {
            try { $NewImage.Dispose() } catch {}
        }
        return
    }

    $oldImage = $Item.Image
    $Item.Image = $NewImage

    if ($oldImage -and -not [object]::ReferenceEquals($oldImage, $NewImage)) {
        try { $oldImage.Dispose() } catch {}
    }
}

function Set-TrayCommandItemVisualState {
    param(
        [System.Windows.Forms.ToolStripMenuItem]$Item,
        [AllowNull()][string]$ChipText,
        [int]$PaddingRight = 64
    )

    if (-not $Item) { return }

    $Item.AccessibleName = "__flyout_command__"
    $Item.AccessibleDescription = if ([string]::IsNullOrWhiteSpace($ChipText)) { "" } else { $ChipText.Trim().ToUpperInvariant() }
    $Item.Padding = New-Object System.Windows.Forms.Padding(0, 0, $PaddingRight, 0)
}

function Set-TrayGameGroupRowVisualState {
    param([System.Windows.Forms.ToolStripMenuItem]$Item)

    if (-not $Item) { return }
    $Item.AccessibleName = "__game_group_row__"
    $Item.AccessibleDescription = ""
    $Item.Padding = New-Object System.Windows.Forms.Padding(0)
}

function Get-TrayMenuWidthBudget {
    $widthBudget = [int]$script:TrayMenuPreferredWidth
    try {
        $screen = [System.Windows.Forms.Screen]::FromPoint([System.Windows.Forms.Cursor]::Position)
        if (-not $screen) { $screen = [System.Windows.Forms.Screen]::PrimaryScreen }
        if ($screen -and $screen.WorkingArea.Width -gt 0) {
            $screenBudget = [Math]::Max([int]$script:TrayMenuMinimumWidth, $screen.WorkingArea.Width - [int]$script:TrayMenuScreenMargin)
            $widthBudget = [Math]::Min($widthBudget, $screenBudget)
        }
    }
    catch {}
    return [Math]::Max([int]$script:TrayMenuMinimumWidth, $widthBudget)
}

function Set-TrayDropDownWidthBudget {
    param([System.Windows.Forms.ToolStripDropDown]$DropDown)

    if (-not $DropDown) { return }

    $widthBudget = Get-TrayMenuWidthBudget
    $minimumWidth = [int]$script:TrayMenuMinimumWidth
    $DropDown.MinimumSize = New-Object System.Drawing.Size($minimumWidth, 0)
    $DropDown.MaximumSize = New-Object System.Drawing.Size($widthBudget, 0)
    $DropDown.AutoSize = $true
}

function Invoke-TrayMenuPulseInvalidation {
    try {
        if ($script:notifyIcon -and $script:notifyIcon.ContextMenuStrip) {
            $menu = $script:notifyIcon.ContextMenuStrip
            if (-not $menu.IsDisposed -and $menu.Visible) {
                $menu.Invalidate()
            }
        }
        foreach ($item in @($script:profileMenuItems)) {
            if (-not $item -or -not $item.Owner) { continue }
            if (-not $item.Owner.IsDisposed -and $item.Owner.Visible) {
                $item.Owner.Invalidate()
            }
        }
    } catch {}
}

function Stop-TrayMenuPulseTimer {
    if ($script:TrayMenuPulseTimer) {
        try { $script:TrayMenuPulseTimer.Stop() } catch {}
        try { $script:TrayMenuPulseTimer.Dispose() } catch {}
        $script:TrayMenuPulseTimer = $null
    }
    $script:TrayMenuPulseFrame = 0
    if ("DarkThemeRenderer" -as [type]) {
        try { [DarkThemeRenderer]::PulseFrame = 0 } catch {}
    }
}

function Start-TrayMenuPulseTimer {
    Stop-TrayMenuPulseTimer
    $script:TrayMenuPulseTimer = New-Object System.Windows.Forms.Timer
    $script:TrayMenuPulseTimer.Interval = 90
    $script:TrayMenuPulseTimer.Add_Tick({
        try {
            $script:TrayMenuPulseFrame = ($script:TrayMenuPulseFrame + 1) % 120
            if ("DarkThemeRenderer" -as [type]) {
                [DarkThemeRenderer]::PulseFrame = $script:TrayMenuPulseFrame
            }
            Invoke-TrayMenuPulseInvalidation
        } catch {
            Stop-TrayMenuPulseTimer
        }
    })
    $script:TrayMenuPulseTimer.Start()
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
    Plays the active theme's apply-success frame sequence, then stays on Active.
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

        # Final frame is the steady active icon
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
    $resolvedId = Resolve-ProfileAlias $ProfileId
    if ($resolvedId -and $resolvedId -ne $ProfileId) {
        Write-TrayLog "Resolved retired profile id '$ProfileId' -> '$resolvedId' via alias map"
        $ProfileId = $resolvedId
    }
    $profile = $script:Profiles[$ProfileId]
    $previousProfileId = $script:activeProfile
    $sameActiveProfile = (
        -not [string]::IsNullOrWhiteSpace($previousProfileId) -and
        $previousProfileId -eq $ProfileId
    )
    $needsNoSyncOsdReminder = Test-NeedsNoSyncOsdReminder -FromProfileId $previousProfileId -ToProfileId $ProfileId

    if (-not $profile) {
        Write-TrayLog "Profile missing from current profile list: $ProfileId" -Level "WARN"
        Play-FailSound
        Set-IconState -State "Warning"
        $missingProfileVisual = Get-TrayProfileToastVisualArgs -ProfileId $ProfileId -Profile $null
        $missingProfileTitle = Get-TrayProfileDisplayName -ProfileId $ProfileId
        Show-Notification @missingProfileVisual -Title $missingProfileTitle -Message "Profile missing from current list." -Type "Warning" -MetaText $ProfileId
        Set-TrayLastAction -Message "Profile missing from current list: $missingProfileTitle"
        Update-MenuState
        return
    }

    if ($sameActiveProfile -and (Complete-SameActiveProfileSelectionIfHandled -ProfileId $ProfileId -Profile $profile)) {
        return
    }
    $profileTitle = Get-TrayProfileObjectDisplayName -Profile $profile -Fallback $ProfileId

    # Show applying state
    Set-IconState -State "Applying"
    Set-TrayOperationTooltipText -Text "computa - Applying..."

    # Show progress overlay
    $progressVisual = Get-TrayProfileToastVisualArgs -ProfileId $ProfileId -Profile $profile
    Show-ProgressOverlay @progressVisual -Title "Applying $profileTitle" -StepText "Initializing..."

    try {
        $tempFile = [System.IO.Path]::GetTempFileName()
        $errFile = "$tempFile.err"

        Update-ProgressOverlay -StepText "Running profile application..."

        if ($sameActiveProfile) {
            $applyArgs = Get-AbsoBackendArgs -CommandArgs @("reapply", "--json")
            Write-TrayLog "Profile '$ProfileId' is already active but verification status is '$script:ActiveProfileVerificationStatus'; using reapply instead of full apply"
        }
        else {
            $applyArgs = Get-AbsoBackendArgs -CommandArgs @("apply", $ProfileId, "--json", "--no-fallback")
        }

        Write-TrayLog "Running: $($script:PythonExe) $($applyArgs -join ' ')"
        $proc = Start-Process -FilePath $script:PythonExe -ArgumentList $applyArgs `
            -NoNewWindow -PassThru -WorkingDirectory $script:ProjectRoot `
            -RedirectStandardOutput $tempFile -RedirectStandardError $errFile
        # PS 5.1: cache the handle now or .ExitCode reads $null after exit.
        if ($proc) { $null = $proc.Handle }

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
            $timeoutVisual = Get-TrayProfileToastVisualArgs -ProfileId $ProfileId -Profile $profile
            $timeoutTitle = $profileTitle
            Show-Notification @timeoutVisual -Title $timeoutTitle -Message "Apply timed out after 120s" -Type "Error" -MetaText $ProfileId
            Set-TrayLastAction -Message "Apply timed out after 120s"
            Update-MenuState
            Remove-Item $tempFile -Force -ErrorAction SilentlyContinue
            Remove-Item $errFile -Force -ErrorAction SilentlyContinue
            return
        }
        $exitCode = $proc.ExitCode
        $proc.Dispose()

        $rawOutput = Get-Content $tempFile -Raw -ErrorAction SilentlyContinue
        $errOutput = Get-Content $errFile -Raw -ErrorAction SilentlyContinue
        Remove-Item $tempFile -Force -ErrorAction SilentlyContinue
        Remove-Item $errFile -Force -ErrorAction SilentlyContinue

        Write-TrayLog "CLI output: $rawOutput"
        if ($errOutput) { Write-TrayLog "CLI stderr: $errOutput" -Level "WARN" }

        if (-not $rawOutput) { throw "No output from CLI" }

        $json = Invoke-JsonSafe -Text $rawOutput -Source 'ApplyProfile'
        if ($null -eq $json) { throw "Apply CLI returned malformed JSON (see tray log for payload preview)" }

        $failedHandlers = @()
        if ($json.data -and $json.data.results) {
            foreach ($r in $json.data.results) {
                if ($r.status -and $r.status -ne "success" -and $r.status -ne "skipped") {
                    $failedHandlers += $r.handler
                }
            }
        }

        $exitCodeOk = ($null -eq $exitCode -or $exitCode -eq 0)
        if ($null -eq $exitCode) {
            Write-TrayLog "Apply CLI exit code was unavailable; falling back to JSON payload validation" -Level "WARN"
        }

        $applySucceeded = (
            $exitCodeOk -and
            $json.success -and
            $json.data -and
            $json.data.success -and
            $failedHandlers.Count -eq 0
        )

        if ($applySucceeded) {
            $appliedProfileId = $ProfileId
            if ($json.data -and $json.data.profile) {
                $appliedProfileId = "$($json.data.profile)"
            }
            $requestedProfileId = $ProfileId
            if ($json.data -and $json.data.requested_profile) {
                $requestedProfileId = "$($json.data.requested_profile)"
            }
            $fallbackApplied = $false
            if ($json.data -and $null -ne $json.data.fallback_applied) {
                $fallbackApplied = [bool]$json.data.fallback_applied
            }
            $appliedProfile = $null
            if ($script:Profiles.Contains($appliedProfileId)) {
                $appliedProfile = $script:Profiles[$appliedProfileId]
            }
            elseif ($appliedProfileId -eq $ProfileId -and $profile) {
                $appliedProfile = $profile
            }
            $appliedDisplayName = if ($appliedProfile -and -not [string]::IsNullOrWhiteSpace("$($appliedProfile.Name)")) {
                Format-TrayDisplayCopy -Text "$($appliedProfile.Name)"
            }
            else {
                Get-TrayProfileDisplayName -ProfileId $appliedProfileId
            }
            $appliedSub = if ($appliedProfile -and -not [string]::IsNullOrWhiteSpace("$($appliedProfile.Sub)")) {
                Format-TrayDisplayCopy -Text "$($appliedProfile.Sub)"
            }
            else {
                ""
            }
            $toastMetaText = $appliedProfileId
            if ($fallbackApplied -and $requestedProfileId -ne $appliedProfileId) {
                $toastMetaText = "$requestedProfileId -> $appliedProfileId"
                Write-TrayLog "Profile fallback applied: requested=$requestedProfileId actual=$appliedProfileId"
            }
            $syncTransition = Get-SyncTransitionDirection -FromProfileId $previousProfileId -ToProfileId $appliedProfileId
            $needsNoSyncOsdReminder = ($syncTransition -eq "to_no_sync")

            $applyWarnings = Get-ApplyWarningMessages -Json $json
            $applyNotices = Get-ApplyNoticeMessages -Json $json
            $applyPostApplyNotes = Get-ApplyPostApplyNoteMessages -Json $json
            $applyActionButtons = Get-ApplyManualActionButtons -Json $json
            $applySummaryLevel = Get-ApplySummaryLevel -Json $json
            # Build the toast body separately from the title. The TITLE is the bare
            # profile display name (clean, no parens, no pipes); the BODY is the
            # applied-profile Sub plus a short caveat list. Caveats are now joined
            # into a single grammatical sentence with a clear separator so the
            # downstream sentence-trimmer in _Derive-ToastBody can't accidentally
            # truncate a multi-caveat message at the first period.
            $toastTitle = $appliedDisplayName
            $msg = if ([string]::IsNullOrWhiteSpace($appliedSub)) { "Applied." } else { "Applied. $appliedSub." }
            $extras = @()
            if ($json.data.requires_reboot) { $extras += "Windows restart required to take full effect" }
            if ($fallbackApplied -and $requestedProfileId -ne $appliedProfileId) {
                $requestedDisplayName = Get-TrayProfileDisplayName -ProfileId $requestedProfileId
                $extras += "Requested '$requestedDisplayName' was unsafe for this display; used safe fallback '$appliedDisplayName'"
            }
            if ($applyWarnings.Count -gt 0) {
                $label = if ($applySummaryLevel -eq "caution") { "Caution" } else { "Warning" }
                $extras += ("${label}: " + $applyWarnings[0])
                if ($applyWarnings.Count -gt 1) {
                    $extras += ("(+$($applyWarnings.Count - 1) more - see tray log)")
                }
            }
            if ($applyNotices.Count -gt 0 -and $applyWarnings.Count -eq 0) {
                $extras += ("Note: " + $applyNotices[0])
                if ($applyNotices.Count -gt 1) {
                    $extras += ("(+$($applyNotices.Count - 1) more - see tray log)")
                }
            }
            if ($applyPostApplyNotes.Count -gt 0) {
                $extras += ("Manual: " + $applyPostApplyNotes[0])
                if ($applyPostApplyNotes.Count -gt 1) {
                    $extras += ("(+$($applyPostApplyNotes.Count - 1) more manual notes - see tray log)")
                }
            }
            # Compose caveats into a sentence rather than just appending the first.
            # Each caveat reads as its own clause and ends with a period so any
            # later concatenation (e.g. DDC/CI confirmation) starts cleanly.
            if ($extras.Count -gt 0) {
                $caveatSentence = ""
                foreach ($extra in $extras) {
                    $clean = "$extra".Trim().TrimEnd('.')
                    if ($caveatSentence) { $caveatSentence += " " }
                    $caveatSentence += ($clean + ".")
                }
                $msg += " " + $caveatSentence
            }
            # Trim trailing whitespace/punctuation drift
            $msg = $msg.Trim()
            $toastProfileVisual = Get-TrayProfileToastVisualArgs `
                -ProfileId $appliedProfileId `
                -Profile $appliedProfile `
                -ActiveBadge

            if ($applySummaryLevel -eq "warning") {
                Write-TrayLog "Profile committed with warnings: $appliedProfileId" -Level "WARN"
                foreach ($warning in $applyWarnings) {
                    Write-TrayLog "Apply warning [$appliedProfileId]: $warning" -Level "WARN"
                }
                Update-ProgressOverlay -StepText "Profile committed with warnings"
            }
            elseif ($applySummaryLevel -eq "caution") {
                Write-TrayLog "Profile applied with cautions: $appliedProfileId"
                foreach ($warning in $applyWarnings) {
                    Write-TrayLog "Apply caution [$appliedProfileId]: $warning"
                }
                Update-ProgressOverlay -StepText "Profile applied with cautions"
            }
            elseif ($applyNotices.Count -gt 0) {
                Write-TrayLog "Profile applied with notices: $appliedProfileId"
                foreach ($notice in $applyNotices) {
                    Write-TrayLog "Apply notice [$appliedProfileId]: $notice"
                }
                Update-ProgressOverlay -StepText "Profile applied with notices"
            }
            else {
                Write-TrayLog "Profile apply completed: $appliedProfileId"
                Update-ProgressOverlay -StepText "Profile apply completed"
            }
            foreach ($note in $applyPostApplyNotes) {
                Write-TrayLog "Apply manual note [$appliedProfileId]: $note"
            }
            if ($applyActionButtons.Count -gt 0) {
                Write-TrayLog "Apply manual actions [$appliedProfileId]: $($applyActionButtons.Count)"
            }

            Start-Sleep -Milliseconds 500
            Close-ProgressOverlay

            # Decide whether ABSO already handled monitor firmware Adaptive Sync via DDC/CI.
            # Preferred signal: the structured `monitor_adaptive_sync_state` field surfaced
            # by ApplyResult.  Fallback (for older backends or non-apply paths): scan the
            # NVIDIA handler's granular `handler_applied_details` list for the marker line.
            # The legacy fallback of scanning top-level `applied_settings` is intentionally
            # dropped — that list only contains handler class names, not setting lines, so
            # the suppression never fired and users got stale "go to your OSD" popups even
            # when ABSO had already disabled Adaptive Sync.
            $ddciDisabled = $false
            $ddciEnabled = $false
            $structuredSyncState = $null
            if ($json.data -and $null -ne $json.data.monitor_adaptive_sync_state) {
                $structuredSyncState = "$($json.data.monitor_adaptive_sync_state)".ToLowerInvariant()
            }
            if ($structuredSyncState -eq "disabled") { $ddciDisabled = $true }
            elseif ($structuredSyncState -eq "enabled") { $ddciEnabled = $true }
            else {
                # Fallback: scan the NVIDIA handler's granular applied lines if the
                # structured field is missing (e.g., reapply path, older backend build).
                $nvidiaApplied = $null
                if ($json.data -and $json.data.handler_applied_details) {
                    $nvidiaApplied = $json.data.handler_applied_details.NvidiaSettingsHandler
                }
                if ($nvidiaApplied) {
                    foreach ($line in $nvidiaApplied) {
                        if ($line -match "Monitor Adaptive Sync:\s*disabled") { $ddciDisabled = $true; break }
                        if ($line -match "Monitor Adaptive Sync:\s*enabled")  { $ddciEnabled  = $true; break }
                    }
                }
            }

            # All branches keep the carefully composed $msg (profile Sub + caveat sentences)
            # so reboot warnings, fallback notes, and apply warnings never get dropped just
            # because a sync-mode transition or DDC/CI signal also triggered a popup.  We
            # APPEND a Sync-Mode clause to $msg rather than overwriting it, and we ensure
            # the append always starts after a clean sentence boundary.
            $msg = $msg.TrimEnd()
            if ($msg -and $msg[-1] -notin @('.', '!', '?')) { $msg += "." }

            if ($needsNoSyncOsdReminder -and -not $ddciDisabled) {
                # DDC/CI did not (or could not) disable the monitor's firmware Adaptive Sync,
                # so the user still has to touch the OSD. Keep the rest of the context but
                # prepend the OSD action so it leads visually.
                $msg = "Turn OFF Adaptive Sync/FreeSync in your monitor OSD for strict No-Sync mode. " + $msg
                Play-VrrWarningSound
                Write-TrayLog "No-Sync OSD reminder shown for transition: $previousProfileId -> $appliedProfileId"
                Play-ApplySuccessIconAnimation
                Show-TrayToast @toastProfileVisual -Title $toastTitle -Message $msg -Type "Warning" -Duration 6000 -MetaText $toastMetaText -ActionButtons @($applyActionButtons) -BypassDedup
            }
            elseif ($needsNoSyncOsdReminder -and $ddciDisabled) {
                # ABSO already disabled monitor Adaptive Sync via DDC/CI — give the user
                # a low-key confirmation instead of the stale "go into your OSD" warning.
                $msg += " ABSO turned OFF monitor Adaptive Sync via DDC/CI."
                Write-TrayLog "Monitor Adaptive Sync auto-disabled via DDC/CI for: $previousProfileId -> $appliedProfileId"
                Play-SuccessSound
                Play-ApplySuccessIconAnimation
                Show-TrayToast @toastProfileVisual -Title $toastTitle -Message $msg -Type "Success" -Duration 5000 -MetaText $toastMetaText -ActionButtons @($applyActionButtons) -BypassDedup
            }
            elseif ($syncTransition -eq "to_sync" -and $ddciEnabled) {
                # Symmetric feedback: tell the user ABSO re-enabled their firmware Adaptive
                # Sync so they aren't left wondering whether they need to touch the OSD.
                $msg += " ABSO turned ON monitor Adaptive Sync via DDC/CI."
                Write-TrayLog "Monitor Adaptive Sync auto-enabled via DDC/CI for: $previousProfileId -> $appliedProfileId"
                Play-SuccessSound
                Play-ApplySuccessIconAnimation
                Show-TrayToast @toastProfileVisual -Title $toastTitle -Message $msg -Type "Success" -Duration 5000 -MetaText $toastMetaText -ActionButtons @($applyActionButtons) -BypassDedup
            }
            elseif ($applySummaryLevel -eq "warning") {
                # Apply succeeded but a real (non-soft) warning was raised. Use the warning
                # sound + amber toast so the user actually realizes something needs attention.
                Play-VrrWarningSound
                Play-ApplySuccessIconAnimation
                Show-TrayToast @toastProfileVisual -Title $toastTitle -Message $msg -Type "Warning" -Duration 6000 -MetaText $toastMetaText -ActionButtons @($applyActionButtons) -BypassDedup
            }
            elseif ($applySummaryLevel -eq "caution") {
                # Soft environmental warnings (mixed refresh, MPO glitch risk, etc.).
                # Render as a Warning-toned toast (amber), not green Success — the user
                # should still notice the caveat without it shouting "error".
                Play-SuccessSound
                Play-ApplySuccessIconAnimation
                Show-TrayToast @toastProfileVisual -Title $toastTitle -Message $msg -Type "Warning" -Duration 6000 -MetaText $toastMetaText -ActionButtons @($applyActionButtons) -BypassDedup
            }
            elseif ($applyNotices.Count -gt 0) {
                Play-SuccessSound
                Play-ApplySuccessIconAnimation
                Show-TrayToast @toastProfileVisual -Title $toastTitle -Message $msg -Type "Success" -Duration 6000 -MetaText $toastMetaText -ActionButtons @($applyActionButtons) -BypassDedup
            }
            else {
                Play-SuccessSound
                Play-ApplySuccessIconAnimation
                Show-TrayToast @toastProfileVisual -Title $toastTitle -Message $msg -Type "Success" -MetaText $toastMetaText -ActionButtons @($applyActionButtons) -BypassDedup
            }

            $script:activeProfile = $appliedProfileId
            Set-ActiveProfileVerificationSeedFromApplyData -Data $json.data
            $script:LastAction = if ($applySummaryLevel -eq "warning") {
                "Applied w/ warnings: $appliedDisplayName"
            }
            elseif ($applySummaryLevel -eq "caution") {
                "Applied w/ cautions: $appliedDisplayName"
            }
            elseif ($applyNotices.Count -gt 0) {
                "Applied w/ notes: $appliedDisplayName"
            }
            else {
                "Applied: $appliedDisplayName"
            }
            $script:LastActionTime = Get-Date

            # Record in history and persist the last known active state for startup arbitration.
            $script:TrayConfig = Add-ProfileHistory -ProfileId $appliedProfileId -ProfileName $appliedDisplayName -Config $script:TrayConfig

            Update-MenuState
            $quickPanelEmpty = Get-QuickPanelEmptyStatus
            $quickPanelPendingApplyText = Get-ActiveProfilePendingApplyText
            $quickPanelWindowsRestartText = Get-ActiveProfileRebootPendingText
            $quickPanelVerificationText = Get-ActiveProfileVerificationInProgressText
            Update-QuickPanel -Favorites $script:TrayConfig.favorites -Profiles $script:Profiles -ActiveProfile $script:activeProfile -ActivePendingApplyText $quickPanelPendingApplyText -ActiveWindowsRestartText $quickPanelWindowsRestartText -ActiveVerificationText $quickPanelVerificationText -EmptyMessage $quickPanelEmpty.Message -EmptyProfileId $quickPanelEmpty.ProfileId -OnApply { param($id) Apply-Profile $id }
            Start-ActiveProfileVerificationTimer -DelayMilliseconds 500
        }
        else {
            $err = Get-ApplyFailureMessage -Json $json -FailedHandlers $failedHandlers -ExitCode $exitCode
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
            # Use the profile name as the toast title; Get-ApplyFailureMessage
            # already returns a concise "Not applied..." sentence with next steps.
            $failureTitle = $profileTitle
            $failureVisual = Get-TrayProfileToastVisualArgs -ProfileId $ProfileId -Profile $profile
            $failureActionButtons = Get-ApplyFailureActionButtons -Message $err -Json $json
            Show-Notification @failureVisual -Title $failureTitle -Message $err -Type $notifyType -MetaText $ProfileId -ActionButtons @($failureActionButtons)
            $script:LastAction = $err
            $script:LastActionTime = Get-Date
            Update-MenuState
        }
    }
    catch {
        Write-TrayLog "Apply-Profile exception: $($_.Exception.Message)" -Level "ERROR"
        Close-ProgressOverlay
        Play-FailSound
        Set-IconState -State "Error"
        $exceptionTitle = $profileTitle
        $exceptionVisual = Get-TrayProfileToastVisualArgs -ProfileId $ProfileId -Profile $profile
        Show-Notification @exceptionVisual -Title $exceptionTitle -Message "Error: $($_.Exception.Message)" -Type "Error" -MetaText $ProfileId
        $script:LastAction = "Error: $($_.Exception.Message)"
        $script:LastActionTime = Get-Date
        Update-MenuState
    }
}

function Apply-PendingProfileFixes {
    param([switch]$Force)

    if ([string]::IsNullOrWhiteSpace([string]$script:activeProfile)) {
        Show-Notification -Title "computa" -Message "No active profile to repair" -Type "Info" -ActionName "Apply" -ActionColor $script:Colors.AccentAmber
        Set-TrayLastAction -Message "No active profile to repair"
        Update-MenuState
        return
    }

    $activeRecord = Get-ActiveTrayProfileRecord
    $pendingText = Get-ActiveProfilePendingApplyText
    if ($script:ActiveProfileVerificationStatus -eq "mismatch") {
        if ([string]::IsNullOrWhiteSpace($pendingText)) {
            $pendingText = "profile mismatch"
        }
        Write-TrayLog "Apply-PendingProfileFixes routing mismatch for '$script:activeProfile' through reapply ($pendingText)"
        Apply-Profile -ProfileId $script:activeProfile
        return
    }
    if ([string]::IsNullOrWhiteSpace($pendingText) -and -not $Force) {
        $pendingNoopVisual = Get-TrayProfileToastVisualArgs `
            -ProfileId $script:activeProfile `
            -Profile $activeRecord.Profile `
            -ActiveBadge
        $pendingNoopTitle = if ($activeRecord.Id) { $activeRecord.DisplayName } else { "computa" }
        Show-Notification @pendingNoopVisual -Title $pendingNoopTitle -Message "No pending profile fixes found" -Type "Info" -MetaText $script:activeProfile
        Set-TrayLastAction -Message "No pending profile fixes found"
        Update-MenuState
        return
    }
    if ([string]::IsNullOrWhiteSpace($pendingText)) {
        $pendingText = "profile verification"
    }

    Write-TrayLog "Apply-PendingProfileFixes called for '$script:activeProfile' ($pendingText)"
    Set-IconState -State "Applying"
    Set-TrayOperationTooltipText -Text "computa - Applying pending profile fixes..."
    $pendingProgressVisual = Get-TrayProfileToastVisualArgs `
        -ProfileId $script:activeProfile `
        -Profile $activeRecord.Profile `
        -ActiveBadge
    Show-ProgressOverlay @pendingProgressVisual -Title "Applying pending profile fixes" -StepText $pendingText

    $tempFile = [System.IO.Path]::GetTempFileName()
    $errFile = "$tempFile.err"
    try {
        $args = Get-AbsoBackendArgs -CommandArgs @("apply-pending", $script:activeProfile, "--json")
        Write-TrayLog "Running: $($script:PythonExe) $($args -join ' ')"
        $proc = Start-Process -FilePath $script:PythonExe -ArgumentList $args `
            -NoNewWindow -PassThru -WorkingDirectory $script:ProjectRoot `
            -RedirectStandardOutput $tempFile -RedirectStandardError $errFile
        # PS 5.1: cache the handle now or .ExitCode reads $null after exit.
        if ($proc) { $null = $proc.Handle }

        $timeout = (Get-Date).AddSeconds(45)
        while (-not $proc.HasExited -and (Get-Date) -lt $timeout) {
            [System.Windows.Forms.Application]::DoEvents()
            Start-Sleep -Milliseconds 100
        }
        if (-not $proc.HasExited) {
            try { $proc.Kill() } catch {}
            throw "apply-pending timed out after 45s"
        }

        $exitCode = $proc.ExitCode
        $proc.Dispose()
        $rawOutput = Get-Content $tempFile -Raw -ErrorAction SilentlyContinue
        $errOutput = Get-Content $errFile -Raw -ErrorAction SilentlyContinue
        if ($errOutput) { Write-TrayLog "apply-pending stderr: $errOutput" -Level "WARN" }
        if (-not $rawOutput) { throw "apply-pending returned no output" }

        $json = Invoke-JsonSafe -Text $rawOutput -Source 'ApplyPending'
        if ($null -eq $json) { throw "apply-pending returned malformed JSON" }
        $exitCodeOk = ($null -eq $exitCode -or $exitCode -eq 0)
        if ($null -eq $exitCode) {
            Write-TrayLog "apply-pending exit code was unavailable; falling back to JSON payload validation" -Level "WARN"
        }
        if (-not $exitCodeOk -or -not $json.success -or -not $json.data -or -not $json.data.success) {
            $err = if ($json.data -and $json.data.error) { $json.data.error } elseif ($json.error) { $json.error } else { "reason not reported" }
            throw $err
        }

        Close-ProgressOverlay
        $changedSettings = @($json.data.changed_settings)
        $requiresReboot = if ($json.data.PSObject.Properties["requires_reboot"]) { [bool]$json.data.requires_reboot } else { $false }
        Set-ActiveProfileVerificationSeedFromApplyData -Data $json.data
        $pendingToastVisual = Get-TrayProfileToastVisualArgs `
            -ProfileId $script:activeProfile `
            -Profile $activeRecord.Profile `
            -ActiveBadge
        $pendingTitle = if ($activeRecord.Id) { $activeRecord.DisplayName } else { "computa" }
        if ($changedSettings.Count -gt 0) {
            Write-TrayLog "Pending profile fixes applied: $($changedSettings -join ', ')"
            Play-SuccessSound
            Play-ApplySuccessIconAnimation
            $message = if ($requiresReboot) {
                "Pending profile fixes applied: $pendingText. Windows restart required."
            }
            else {
                "Pending profile fixes applied: $pendingText."
            }
            Show-TrayToast @pendingToastVisual -Title $pendingTitle -Message $message -Type "Success" -MetaText $script:activeProfile
            $script:LastAction = if ($requiresReboot) { "Windows restart required: $pendingText" } else { "Fixed: $pendingText" }
        }
        else {
            Write-TrayLog "apply-pending succeeded with no write needed"
            Show-Notification @pendingToastVisual -Title $pendingTitle -Message "No pending profile fix was needed" -Type "Info" -MetaText $script:activeProfile
            $script:LastAction = "No pending profile fix needed"
        }
        $script:LastActionTime = Get-Date
        Start-ActiveProfileVerificationTimer -DelayMilliseconds 500
        Update-MenuState
    }
    catch {
        Close-ProgressOverlay
        Write-TrayLog "Apply-PendingProfileFixes failed: $($_.Exception.Message)" -Level "ERROR"
        Play-FailSound
        Set-IconState -State "Error"
        $activeRecord = Get-ActiveTrayProfileRecord
        $pendingFailureVisual = Get-TrayProfileToastVisualArgs `
            -ProfileId $script:activeProfile `
            -Profile $activeRecord.Profile `
            -ActiveBadge
        $pendingFailureTitle = if ($activeRecord.Id) { $activeRecord.DisplayName } else { "computa" }
        Show-Notification @pendingFailureVisual -Title $pendingFailureTitle -Message "Pending profile fixes failed: $($_.Exception.Message)" -Type "Error" -MetaText $script:activeProfile
        $script:LastAction = "Pending profile fixes failed: $($_.Exception.Message)"
        $script:LastActionTime = Get-Date
        Update-MenuState
    }
    finally {
        Remove-Item $tempFile -Force -ErrorAction SilentlyContinue
        Remove-Item $errFile -Force -ErrorAction SilentlyContinue
    }
}

function Get-TrayCommandFilePath {
    return (Join-Path (Get-InstalledAppRoot) "tray-command.json")
}

function Invoke-TrayCommandFile {
    $commandPath = Get-TrayCommandFilePath
    if (-not (Test-Path $commandPath)) { return }

    try {
        $raw = Get-Content $commandPath -Raw -ErrorAction Stop
        Remove-Item $commandPath -Force -ErrorAction SilentlyContinue
        $payload = Invoke-JsonSafe -Text $raw -Source 'TrayCommand'
        if ($null -eq $payload) {
            Write-TrayLog "Tray command file ignored: malformed JSON" -Level "WARN"
            return
        }

        $command = if ($payload.command) { "$($payload.command)" } else { "" }
        if ($command -notin @("apply_pending", "repair_startup")) {
            Write-TrayLog "Tray command file ignored: unsupported command '$command'" -Level "WARN"
            return
        }

        if ($command -eq "repair_startup") {
            Write-TrayLog "Tray command file accepted: repair_startup"
            [void](Repair-StartupRegistration -Force)
            return
        }

        $requestedProfile = if ($payload.profile) { Resolve-ProfileAlias "$($payload.profile)" } else { $script:activeProfile }
        if ([string]::IsNullOrWhiteSpace($requestedProfile)) {
            Write-TrayLog "Tray command apply_pending ignored: no active/requested profile" -Level "WARN"
            return
        }
        if ($requestedProfile -ne $script:activeProfile) {
            Write-TrayLog "Tray command apply_pending ignored: requested '$requestedProfile' but active is '$script:activeProfile'" -Level "WARN"
            return
        }

        Write-TrayLog "Tray command file accepted: apply_pending for '$requestedProfile'"
        Apply-PendingProfileFixes -Force
    }
    catch {
        Write-TrayLog "Tray command file failed: $($_.Exception.Message)" -Level "ERROR"
    }
}

function Restore-Settings {
    Set-IconState -State "Applying"
    Set-TrayOperationTooltipText -Text "computa - Restoring..."
    Show-ProgressOverlay `
        -Title "Restoring Settings" `
        -StepText "Restoring previous configuration..." `
        -ActionName "Restore" `
        -ActionColor $script:Colors.AccentPurple

    try {
        $tempFile = [System.IO.Path]::GetTempFileName()
        $errFile = "$tempFile.err"

        $proc = Start-Process -FilePath $script:PythonExe -ArgumentList (Get-AbsoBackendArgs -CommandArgs @("restore", "latest", "--json")) `
            -NoNewWindow -PassThru -WorkingDirectory $script:ProjectRoot `
            -RedirectStandardOutput $tempFile -RedirectStandardError $errFile
        # PS 5.1: cache the handle now or .ExitCode reads $null after exit.
        if ($proc) { $null = $proc.Handle }

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
            Show-Notification -Title "computa" -Message "Restore timed out after 120s" -Type "Error" -ActionName "Restore" -ActionColor $script:Colors.AccentAmber
            Set-IconState -State "Error"
            Set-TrayLastAction -Message "Restore timed out after 120s"
            Update-MenuState
            Remove-Item $tempFile -Force -ErrorAction SilentlyContinue
            Remove-Item $errFile -Force -ErrorAction SilentlyContinue
            return
        }
        $exitCode = $proc.ExitCode
        $proc.Dispose()
        $rawOutput = Get-Content $tempFile -Raw -ErrorAction SilentlyContinue
        $errOutput = Get-Content $errFile -Raw -ErrorAction SilentlyContinue
        Remove-Item $tempFile -Force -ErrorAction SilentlyContinue
        Remove-Item $errFile -Force -ErrorAction SilentlyContinue
        if ($errOutput) { Write-TrayLog "Restore CLI stderr: $errOutput" -Level "WARN" }

        if (-not $rawOutput) { throw "runtime returned no restore status" }

        $json = Invoke-JsonSafe -Text $rawOutput -Source 'Restore'
        if ($null -eq $json) { throw "Restore CLI returned malformed JSON (see tray log for payload preview)" }

        $exitCodeOk = ($null -eq $exitCode -or $exitCode -eq 0)
        if ($null -eq $exitCode) {
            Write-TrayLog "Restore CLI exit code was unavailable; falling back to JSON payload validation" -Level "WARN"
        }

        if ($exitCodeOk -and $json.success -and $json.data -and $json.data.success) {
            Close-ProgressOverlay
            Show-Notification -Title "computa" -Message "Settings restored" -Type "Success" -ActionName "Restore" -ActionColor $script:Colors.AccentGreen
            $script:activeProfile = $null
            Reset-ActiveProfileVerificationState
            Set-TrayLastAction -Message "Restored settings"
            $script:TrayConfig = Set-LastProfileState -Config $script:TrayConfig -Status "restored" -Source "tray_restore"
            Set-IconState -State "Idle"
            Update-MenuState
        }
        else {
            $restoreError = if ($json.error) {
                $json.error
            }
            elseif ($json.data -and $json.data.message) {
                $json.data.message
            }
            else {
                "Backend reported restore failure without a detailed error message (exit code: $(Get-ExitCodeDescriptor -ExitCode $exitCode))"
            }
            Close-ProgressOverlay
            Show-Notification -Title "computa" -Message "Restore failed: $restoreError" -Type "Error" -ActionName "Restore" -ActionColor $script:Colors.AccentAmber
            Set-IconState -State "Error"
            Set-TrayLastAction -Message "Restore failed: $restoreError"
            Update-MenuState
        }
    }
    catch {
        Close-ProgressOverlay
        Show-Notification -Title "computa" -Message "Restore failed: $($_.Exception.Message)" -Type "Error" -ActionName "Restore" -ActionColor $script:Colors.AccentAmber
        Set-IconState -State "Error"
        Set-TrayLastAction -Message "Restore failed: $($_.Exception.Message)"
        Update-MenuState
    }
    Restore-TrayTooltipFromState
}

# ============================================================================
# MENU STATE
# ============================================================================

function Update-MenuState {
    $fullRefresh = -not $script:MenuStateInitialized
    $previousRenderedActive = $script:LastRenderedActiveProfile

    foreach ($item in $script:profileMenuItems) {
        $isActive = ($item.Tag -eq $script:activeProfile)
        $wasActive = ($item.Tag -eq $previousRenderedActive)
        $needsVisualRefresh = $fullRefresh -or $isActive -or $wasActive
        $item.Checked = $isActive

        $p = $script:Profiles[$item.Tag]
        if (-not $p) { continue }
        $catColor = Get-CategoryColor -Category $p.Cat -Fallback $script:Colors.Text
        $gameColor = Get-TrayProfileAccentColor -ProfileId $item.Tag -Profile $p -Fallback $catColor

        # Items inside submenus (OwnerItem is a ToolStripMenuItem) vs top-level items
        $inSubmenu = ($null -ne $item.OwnerItem -and $item.OwnerItem -is [System.Windows.Forms.ToolStripMenuItem])

        if (-not $needsVisualRefresh) { continue }

        try {
            $item.Text = Get-ProfileMenuDisplayText -ProfileId $item.Tag -InSubmenu $inSubmenu
            Set-TrayProfileMenuItemMetadata -Item $item -ProfileId $item.Tag -Profile $p
            $showSyncBadge = ($item.AccessibleName -eq "__profile_menu_item__")
            $favoriteBadge = (Test-Favorite -ProfileId $item.Tag -Config $script:TrayConfig)
            if ($isActive) {
                $newImage = New-TrayProfileMenuImage `
                    -ProfileId $item.Tag `
                    -IsActive $true `
                    -InSubmenu $inSubmenu `
                    -ShowSyncBadge $showSyncBadge `
                    -FavoriteBadge $favoriteBadge
                Set-MenuItemImageSafe -Item $item -NewImage $newImage
                $item.ForeColor = [System.Drawing.Color]::FromArgb(
                    255,
                    [Math]::Min(255, $gameColor.R + 30),
                    [Math]::Min(255, $gameColor.G + 30),
                    [Math]::Min(255, $gameColor.B + 30)
                )
                $item.Font = $script:FontBold
                $item.BackColor = Blend-Color -Base $script:Colors.Background -Overlay $gameColor -Ratio 0.15
            }
            else {
                $newImage = New-TrayProfileMenuImage `
                    -ProfileId $item.Tag `
                    -IsActive $false `
                    -InSubmenu $inSubmenu `
                    -ShowSyncBadge $showSyncBadge `
                    -FavoriteBadge $favoriteBadge
                Set-MenuItemImageSafe -Item $item -NewImage $newImage
                $item.ForeColor = $gameColor
                $item.Font = $script:FontNormal
                $item.BackColor = $script:Colors.Background
            }
        }
        catch {
            Write-TrayLog "Update-MenuState icon error for $($item.Tag): $($_.Exception.Message)" -Level "ERROR"
        }
    }
    if ($script:restoreItem) { $script:restoreItem.Enabled = ($null -ne $script:activeProfile) }
    if ($script:applyPendingItem) {
        $pendingApplyTextForAction = Get-ActiveProfilePendingApplyText
        $pendingFixCheckingText = Get-ActiveProfileVerificationInProgressText
        $pendingFixChecking = (
            $null -ne $script:activeProfile -and
            -not [string]::IsNullOrWhiteSpace($pendingFixCheckingText)
        )
        $script:applyPendingItem.Enabled = (
            $null -ne $script:activeProfile -and
            -not [string]::IsNullOrWhiteSpace($pendingApplyTextForAction)
        )
        $script:applyPendingItem.Visible = ($script:applyPendingItem.Enabled -or $pendingFixChecking)
        if ($script:applyPendingItem.Enabled) {
            if ($script:ActiveProfileVerificationStatus -eq "mismatch") {
                $script:applyPendingItem.Text = "Reapply Active Profile: $pendingApplyTextForAction"
                $script:applyPendingItem.ToolTipText = "Verifier mismatch: $pendingApplyTextForAction. Reapply the active profile to write the current target settings."
                $script:applyPendingItem.AccessibleDescription = "PROFILE MISMATCH"
            }
            else {
                $script:applyPendingItem.Text = "Apply Pending Fixes: $pendingApplyTextForAction"
                $script:applyPendingItem.ToolTipText = "Targeted verifier fix: $pendingApplyTextForAction. No backup, baseline restore, or display reset."
                $script:applyPendingItem.AccessibleDescription = "PENDING FIXES"
            }
            Set-MenuItemImageSafe -Item $script:applyPendingItem -NewImage (New-ActionBitmap -Action "PendingFix" -Color $script:Colors.AccentAmber)
        }
        elseif ($pendingFixChecking) {
            $script:applyPendingItem.Text = "Checking Pending Fixes"
            $script:applyPendingItem.ToolTipText = "Verifier is reading current settings; pending fixes will appear here if found."
            $script:applyPendingItem.AccessibleDescription = "CHECKING PENDING FIXES"
            Set-MenuItemImageSafe -Item $script:applyPendingItem -NewImage (New-ActionBitmap -Action "PendingFix" -Color $script:Colors.AccentBlue)
        }
        else {
            $script:applyPendingItem.Text = "Apply Pending Fixes"
            $script:applyPendingItem.ToolTipText = "No verifier-reported pending fixes for the active profile"
            $script:applyPendingItem.AccessibleDescription = "NO PENDING FIXES"
            Set-MenuItemImageSafe -Item $script:applyPendingItem -NewImage (New-ActionBitmap -Action "PendingFix" -Color $script:Colors.TextDisabled)
        }
    }

    Restore-TrayTooltipFromState
    Set-TrayActiveStatusItemFromState

    # Update status bar
    if ($script:statusBarItem) {
        $statusParts = [System.Collections.Generic.List[string]]::new()
        $pendingApplyText = Get-ActiveProfilePendingApplyText
        $rebootPendingText = Get-ActiveProfileRebootPendingText
        $verificationProgressText = Get-ActiveProfileVerificationInProgressText
        $statusIsVerificationMismatch = ($script:ActiveProfileVerificationStatus -eq "mismatch")
        if ($pendingApplyText) {
            $pendingStatusLabel = if ($statusIsVerificationMismatch) { "Profile mismatch" } else { "Pending profile fix" }
            Add-UniqueTrayMessage -Target $statusParts -Message "${pendingStatusLabel}: $pendingApplyText"
        }
        if ($rebootPendingText) { Add-UniqueTrayMessage -Target $statusParts -Message "Windows restart required: $rebootPendingText" }
        if ($verificationProgressText) { Add-UniqueTrayMessage -Target $statusParts -Message "Checking profile state" }
        $lastActionText = Normalize-TrayLastActionMessage -Message $script:LastAction
        $statusBarLastActionText = $lastActionText
        if (
            $statusIsVerificationMismatch -and
            -not [string]::IsNullOrWhiteSpace($statusBarLastActionText) -and
            $statusBarLastActionText.StartsWith("Profile mismatch:")
        ) {
            $statusBarLastActionText = $null
        }
        if ($statusBarLastActionText) { Add-UniqueTrayMessage -Target $statusParts -Message $statusBarLastActionText }
        $lastActionTimeMessage = Get-TrayLastActionTimeMessage -Value $script:LastActionTime
        $statusShouldShowActionTime = (
            $lastActionTimeMessage -and
            [string]::IsNullOrWhiteSpace($pendingApplyText) -and
            [string]::IsNullOrWhiteSpace($rebootPendingText) -and
            [string]::IsNullOrWhiteSpace($verificationProgressText) -and
            $statusParts.Count -lt 2
        )
        if ($statusShouldShowActionTime) { Add-UniqueTrayMessage -Target $statusParts -Message $lastActionTimeMessage }
        $backupTime = Get-LastBackupTime
        $statusHasBackup = ($backupTime -ne "Never")
        if ($statusHasBackup -and $statusParts.Count -lt 2) { Add-UniqueTrayMessage -Target $statusParts -Message "Backup: $backupTime" }
        $statusBarText = if ($statusParts.Count -gt 0) { @($statusParts) -join '  |  ' } else { "Ready" }
        $script:statusBarItem.Text = "  $statusBarText"
        $script:statusBarItem.ForeColor = [System.Drawing.Color]::FromArgb(255, 95, 127, 127)
        $script:statusBarItem.AccessibleDescription = Get-TrayStatusBarChipText `
            -PendingApplyText $pendingApplyText `
            -RebootPendingText $rebootPendingText `
            -VerificationProgressText $verificationProgressText `
            -LastActionText $statusBarLastActionText `
            -HasBackup $statusHasBackup
        $statusImage = New-TrayStatusBarImage `
            -PendingApplyText $pendingApplyText `
            -RebootPendingText $rebootPendingText `
            -VerificationProgressText $verificationProgressText `
            -ProfileId $script:activeProfile `
            -LastActionText $statusBarLastActionText `
            -FallbackColor $script:statusBarItem.ForeColor
        Set-MenuItemImageSafe -Item $script:statusBarItem -NewImage $statusImage
    }

    $script:LastRenderedActiveProfile = $script:activeProfile
    $script:MenuStateInitialized = $true
}

# ============================================================================
# SYSTEM INFO
# ============================================================================

function Ensure-TrayDisplaySettingsReader {
    if ("Abso.Tray.DisplaySettingsReader" -as [type]) { return $true }
    if ($script:TrayDisplaySettingsReaderUnavailable) { return $false }

    try {
        Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;

namespace Abso.Tray {
    public static class DisplaySettingsReader {
        private const int ENUM_CURRENT_SETTINGS = -1;

        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Ansi)]
        public struct DEVMODE {
            [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)] public string dmDeviceName;
            public short dmSpecVersion;
            public short dmDriverVersion;
            public short dmSize;
            public short dmDriverExtra;
            public int dmFields;
            public int dmPositionX;
            public int dmPositionY;
            public int dmDisplayOrientation;
            public int dmDisplayFixedOutput;
            public short dmColor;
            public short dmDuplex;
            public short dmYResolution;
            public short dmTTOption;
            public short dmCollate;
            [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)] public string dmFormName;
            public short dmLogPixels;
            public int dmBitsPerPel;
            public int dmPelsWidth;
            public int dmPelsHeight;
            public int dmDisplayFlags;
            public int dmDisplayFrequency;
            public int dmICMMethod;
            public int dmICMIntent;
            public int dmMediaType;
            public int dmDitherType;
            public int dmReserved1;
            public int dmReserved2;
            public int dmPanningWidth;
            public int dmPanningHeight;
        }

        [DllImport("user32.dll", CharSet = CharSet.Ansi)]
        private static extern bool EnumDisplaySettings(string deviceName, int modeNum, ref DEVMODE devMode);

        public static int GetCurrentRefreshRate(string deviceName) {
            DEVMODE mode = new DEVMODE();
            mode.dmSize = (short)Marshal.SizeOf(typeof(DEVMODE));
            return EnumDisplaySettings(deviceName, ENUM_CURRENT_SETTINGS, ref mode) ? mode.dmDisplayFrequency : 0;
        }
    }
}
"@ -ErrorAction Stop
        return $true
    }
    catch {
        $script:TrayDisplaySettingsReaderUnavailable = $true
        if (-not $script:TrayDisplaySettingsReaderWarned) {
            Write-TrayLog "Failed to load display settings reader: $($_.Exception.Message)" -Level "WARN"
            $script:TrayDisplaySettingsReaderWarned = $true
        }
        return $false
    }
}

function ConvertTo-TrayRefreshRate {
    param([AllowNull()][object]$Rate)

    if ($null -eq $Rate -or [string]::IsNullOrWhiteSpace("$Rate")) { return $null }

    try {
        $numeric = [double]::Parse("$Rate", [System.Globalization.CultureInfo]::InvariantCulture)
    }
    catch {
        return $null
    }

    if ($numeric -le 1) { return $null }

    $commonRates = @(24, 30, 48, 50, 60, 72, 75, 90, 100, 120, 144, 165, 170, 175, 180, 200, 240, 280, 300, 360, 480)
    foreach ($commonRate in $commonRates) {
        if ([Math]::Abs($numeric - $commonRate) -le 1.0) { return [int]$commonRate }
    }

    return [int][Math]::Round($numeric, 0)
}

function Format-TrayRefreshRate {
    param([AllowNull()][object]$Rate)

    $normalized = ConvertTo-TrayRefreshRate -Rate $Rate
    if ($null -eq $normalized) { return $null }
    return "{0}Hz" -f $normalized
}

function Get-TrayScreenRefreshSnapshot {
    param([AllowNull()][object[]]$Screens)

    if (-not $Screens) {
        try {
            $Screens = @([System.Windows.Forms.Screen]::AllScreens)
        }
        catch {
            Write-TrayLog "Failed to enumerate screens: $($_.Exception.Message)" -Level "WARN"
            return @()
        }
    }

    $apiReady = Ensure-TrayDisplaySettingsReader
    $snapshot = @()
    foreach ($screen in @($Screens)) {
        $rate = $null
        if ($apiReady -and $screen -and -not [string]::IsNullOrWhiteSpace("$($screen.DeviceName)")) {
            try {
                $rate = [Abso.Tray.DisplaySettingsReader]::GetCurrentRefreshRate("$($screen.DeviceName)")
            }
            catch {
                if (-not $script:TrayDisplaySettingsReaderWarned) {
                    Write-TrayLog "Failed to read display refresh for $($screen.DeviceName): $($_.Exception.Message)" -Level "WARN"
                    $script:TrayDisplaySettingsReaderWarned = $true
                }
            }
        }

        $normalizedRate = ConvertTo-TrayRefreshRate -Rate $rate
        $snapshot += [pscustomobject]@{
            DeviceName = if ($screen) { "$($screen.DeviceName)" } else { "" }
            Primary = if ($screen) { [bool]$screen.Primary } else { $false }
            RefreshRate = $normalizedRate
            RefreshText = if ($null -ne $normalizedRate) { "{0}Hz" -f $normalizedRate } else { $null }
        }
    }

    return @($snapshot)
}

function Get-TrayDisplaySummary {
    param([AllowNull()][object]$FallbackRefreshRate)

    $fallbackText = Format-TrayRefreshRate -Rate $FallbackRefreshRate
    try {
        $screens = @([System.Windows.Forms.Screen]::AllScreens)
    }
    catch {
        if ($fallbackText) { return $fallbackText }
        return "Display status not reported"
    }

    $screenCount = @($screens).Count
    if ($screenCount -le 0) {
        if ($fallbackText) { return $fallbackText }
        return "Display status not reported"
    }

    $refreshRecords = Get-TrayScreenRefreshSnapshot -Screens $screens
    $rateLabels = @(
        $refreshRecords |
            Where-Object { $null -ne $_.RefreshRate -and -not [string]::IsNullOrWhiteSpace("$($_.RefreshText)") } |
            Sort-Object RefreshRate -Descending |
            Select-Object -ExpandProperty RefreshText -Unique
    )

    if ($screenCount -gt 1) {
        if ($rateLabels.Count -gt 1) {
            return "$screenCount displays - $($rateLabels -join '/') mixed"
        }
        if ($rateLabels.Count -eq 1) {
            return "$screenCount displays - $($rateLabels[0])"
        }
        if ($fallbackText) {
            return "$screenCount displays - adapter $fallbackText"
        }
        return "$screenCount displays"
    }

    if ($rateLabels.Count -ge 1) { return "$($rateLabels[0])" }
    if ($fallbackText) { return $fallbackText }
    return "Display status not reported"
}

function New-TrayDisplayTopologyBitmap {
    <#
    .SYNOPSIS
    Builds a compact system-info icon from the already computed display summary.
    It does not probe display state; it only visualizes text like
    "2 displays - 300Hz/60Hz mixed" or "300Hz".
    #>
    param(
        [AllowNull()][string]$DisplaySummary,
        [System.Drawing.Color]$Color = [System.Drawing.Color]::White
    )

    $summary = if ([string]::IsNullOrWhiteSpace($DisplaySummary)) { "Display status not reported" } else { "$DisplaySummary" }
    $displayCount = 0
    if ($summary -match '^\s*(\d+)\s+displays\b') {
        try { $displayCount = [Math]::Max(0, [int]$matches[1]) } catch { $displayCount = 0 }
    }
    elseif ($summary -match '\d+\s*Hz' -or $summary -notmatch '(?i)unknown|not reported') {
        $displayCount = 1
    }
    $isMixed = ($summary -match '(?i)\bmixed\b' -or $summary -match '\d+\s*Hz\s*/\s*\d+\s*Hz')
    $hasRate = ($summary -match '\d+\s*Hz')

    $bmp = New-Object System.Drawing.Bitmap(16, 16)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $g.Clear([System.Drawing.Color]::Transparent)

    $glowBrush = New-Object System.Drawing.SolidBrush(
        [System.Drawing.Color]::FromArgb(34, $Color.R, $Color.G, $Color.B)
    )
    $screenBrush = New-Object System.Drawing.SolidBrush(
        [System.Drawing.Color]::FromArgb(230, $Color.R, $Color.G, $Color.B)
    )
    $dimBrush = New-Object System.Drawing.SolidBrush(
        [System.Drawing.Color]::FromArgb(120, $Color.R, $Color.G, $Color.B)
    )
    $innerBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(190, 5, 19, 23))
    $accent = if ($isMixed) { $script:Colors.AccentAmber } elseif ($hasRate) { $script:Colors.AccentTeal } else { $Color }
    # Defensive: never let a missing/undefined theme color reach SolidBrush (a
    # null color throws "constructor not found" and takes down tray startup).
    if ($null -eq $accent) { $accent = $Color }
    $accentBrush = New-Object System.Drawing.SolidBrush($accent)
    $accentPen = New-Object System.Drawing.Pen($accent, 1.05)
    $accentPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
    $accentPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
    $standBrush = New-Object System.Drawing.SolidBrush($Color)
    $textBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::White)
    $font = New-Object System.Drawing.Font("Segoe UI", 5.5, [System.Drawing.FontStyle]::Bold)
    $format = New-Object System.Drawing.StringFormat
    $format.Alignment = [System.Drawing.StringAlignment]::Center
    $format.LineAlignment = [System.Drawing.StringAlignment]::Center

    try {
        $g.FillEllipse($glowBrush, 1, 1, 14, 14)

        if ($displayCount -le 0) {
            $g.FillRectangle($dimBrush, 3, 4, 10, 7)
            $g.FillRectangle($innerBrush, 4, 5, 8, 4)
            $g.DrawString("?", $font, $textBrush, (New-Object System.Drawing.RectangleF(3, 3, 10, 9)), $format)
        }
        elseif ($displayCount -gt 1) {
            $g.FillRectangle($dimBrush, 2, 4, 8, 6)
            $g.FillRectangle($innerBrush, 3, 5, 6, 3)
            $g.FillRectangle($screenBrush, 6, 2, 9, 8)
            $g.FillRectangle($innerBrush, 7, 3, 7, 5)
            $g.FillRectangle($standBrush, 5, 11, 2, 2)
            $g.FillRectangle($standBrush, 11, 10, 2, 3)
            $g.FillRectangle($standBrush, 3, 13, 6, 1)
            $g.FillRectangle($standBrush, 9, 13, 6, 1)
        }
        else {
            $g.FillRectangle($screenBrush, 2, 3, 12, 8)
            $g.FillRectangle($innerBrush, 3, 4, 10, 5)
            $g.FillRectangle($standBrush, 7, 11, 2, 2)
            $g.FillRectangle($standBrush, 5, 13, 6, 1)
        }

        if ($hasRate) {
            $g.DrawLine($accentPen, 4, 7, 6, 5.5)
            $g.DrawLine($accentPen, 6, 5.5, 8, 8.2)
            $g.DrawLine($accentPen, 8, 8.2, 11, 5.6)
        }

        if ($isMixed) {
            $g.FillEllipse($accentBrush, 10, 0, 5, 5)
            $g.DrawLine($accentPen, 12.5, 1.2, 12.5, 3.0)
            $g.DrawLine($accentPen, 12.5, 3.8, 12.5, 3.9)
        }
        elseif ($displayCount -gt 1) {
            $g.FillEllipse($accentBrush, 11, 1, 4, 4)
        }
    }
    finally {
        $format.Dispose()
        $font.Dispose()
        $textBrush.Dispose()
        $standBrush.Dispose()
        $accentPen.Dispose()
        $accentBrush.Dispose()
        $innerBrush.Dispose()
        $dimBrush.Dispose()
        $screenBrush.Dispose()
        $glowBrush.Dispose()
        $g.Dispose()
    }

    return $bmp
}

function Get-SystemInfo {
    $info = @{
        GPU = "GPU not reported"
        Monitor = "Display not reported"
        RefreshRate = "Refresh rate not reported"
        DisplaySummary = "Display status not reported"
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

        $fallbackRefreshRate = $null
        if ($realGpu -and $realGpu.CurrentRefreshRate) {
            $fallbackRefreshRate = $realGpu.CurrentRefreshRate
            $info.RefreshRate = Format-TrayRefreshRate -Rate $fallbackRefreshRate
        }

        $info.DisplaySummary = Get-TrayDisplaySummary -FallbackRefreshRate $fallbackRefreshRate
    }
    catch {
        Write-TrayLog "Failed to get system info: $($_.Exception.Message)" -Level "WARN"
    }

    return $info
}

function Get-TraySystemInfoChipText {
    param(
        [AllowNull()][string]$GpuName,
        [AllowNull()][string]$DisplaySummary
    )

    $chips = [System.Collections.Generic.List[string]]::new()
    $gpuText = if ([string]::IsNullOrWhiteSpace($GpuName)) { "" } else { "$GpuName" }
    $displayText = if ([string]::IsNullOrWhiteSpace($DisplaySummary)) { "" } else { "$DisplaySummary" }
    $gpuReported = (-not [string]::IsNullOrWhiteSpace($gpuText) -and $gpuText -notmatch '(?i)unknown|not reported')
    $displayReported = (-not [string]::IsNullOrWhiteSpace($displayText) -and $displayText -notmatch '(?i)unknown|not reported')

    if ($gpuReported) { [void]$chips.Add("GPU") }
    if ($displayReported) {
        [void]$chips.Add("DISPLAY")
        if ($displayText -match '(?i)\bmixed\b' -or $displayText -match '\d+\s*Hz\s*/\s*\d+\s*Hz') {
            [void]$chips.Add("MIXED")
        }
        elseif ($displayText -match '\d+\s*Hz') {
            [void]$chips.Add("HZ")
        }
    }
    if ($chips.Count -eq 0) { [void]$chips.Add("NO-DATA") }
    return (@($chips) -join "|")
}

function ConvertTo-TrayDateTime {
    param([AllowNull()][object]$Value)

    if ($null -eq $Value -or [string]::IsNullOrWhiteSpace("$Value")) {
        return $null
    }

    if ($Value -is [DateTime]) {
        return [DateTime]$Value
    }

    try {
        return [DateTime]::Parse("$Value", [System.Globalization.CultureInfo]::InvariantCulture)
    }
    catch {
        return $null
    }
}

function Format-TrayTimestamp {
    param([AllowNull()][object]$Value)

    $dt = ConvertTo-TrayDateTime -Value $Value
    if (-not $dt) { return "time unknown" }

    if ($dt.Year -eq (Get-Date).Year) {
        return $dt.ToString("MMM d HH:mm", [System.Globalization.CultureInfo]::InvariantCulture)
    }
    return $dt.ToString("yyyy MMM d HH:mm", [System.Globalization.CultureInfo]::InvariantCulture)
}

function Set-TrayLastAction {
    param([AllowNull()][string]$Message)

    if ([string]::IsNullOrWhiteSpace($Message)) {
        $script:LastAction = $null
        $script:LastActionTime = $null
        return
    }

    $script:LastAction = Normalize-TrayLastActionMessage -Message $Message
    $script:LastActionTime = Get-Date
}

function Normalize-TrayLastActionMessage {
    param([AllowNull()][string]$Message)

    if ([string]::IsNullOrWhiteSpace($Message)) { return $null }

    $text = "$Message".Trim()
    if ($text -match '(?i)^Restart required:\s*(.+)$') {
        return "Windows restart required: $($Matches[1].Trim())"
    }
    if ($text -match '(?i)^Restart required$') {
        return "Windows restart required"
    }
    if ($text -match '(?i)^Needs apply:\s*(.+)$') {
        return "Pending profile fix: $($Matches[1].Trim())"
    }
    if ($text -match '(?i)^Needs apply$') {
        return "Pending profile fix"
    }
    return $text
}

function Get-TrayLastActionTimeMessage {
    param([AllowNull()][object]$Value)

    $displayTime = Format-TrayTimestamp -Value $Value
    if ($displayTime -eq "time unknown") { return $null }
    return "Action: $displayTime"
}

function Get-TrayStatusBarChipText {
    param(
        [AllowNull()][string]$PendingApplyText,
        [AllowNull()][string]$RebootPendingText,
        [AllowNull()][string]$VerificationProgressText,
        [AllowNull()][string]$LastActionText,
        [bool]$HasBackup = $false,
        [bool]$Preview = $false
    )

    $chips = [System.Collections.Generic.List[string]]::new()
    if ($Preview) { [void]$chips.Add("PREVIEW") }
    if (-not [string]::IsNullOrWhiteSpace($PendingApplyText)) { [void]$chips.Add("FIX") }
    if (-not [string]::IsNullOrWhiteSpace($RebootPendingText)) { [void]$chips.Add("RESTART") }
    if (-not [string]::IsNullOrWhiteSpace($VerificationProgressText)) { [void]$chips.Add("CHECK") }
    if (-not [string]::IsNullOrWhiteSpace($LastActionText)) { [void]$chips.Add("ACTION") }
    if ($HasBackup) { [void]$chips.Add("BACKUP") }
    if ($chips.Count -eq 0) { [void]$chips.Add("READY") }
    return (@($chips) -join "|")
}

function New-TrayLastActionStatusBitmap {
    param(
        [AllowNull()][string]$LastActionText,
        [AllowNull()][System.Drawing.Color]$FallbackColor
    )

    if ([string]::IsNullOrWhiteSpace($LastActionText)) { return $null }

    $text = Normalize-TrayLastActionMessage -Message $LastActionText
    $dimColor = if ($FallbackColor) { $FallbackColor } else { $script:Colors.TextDim }
    $action = $null
    $color = $dimColor

    switch -Regex ($text) {
        '^(Pending profile fix|Profile mismatch|No active profile to repair|No pending profile fixes|No pending profile fix|Pending profile fixes|Fixed:)' {
            $action = "PendingFix"; $color = $script:Colors.AccentAmber; break
        }
        '^(Windows restart required)' {
            $action = "WindowsRestart"; $color = $script:Colors.AccentAmber; break
        }
        '^(Restored|Restore|Restore hotkey)' {
            $action = "Restore"; $color = $script:Colors.AccentPurple; break
        }
        '^(Audit|Verify|Verification)' {
            $action = "Audit"; $color = $script:Colors.AccentBlue; break
        }
        '^(Startup)' {
            $action = "Startup"
            $color = if ($text -match '(?i)failed|warning') { $script:Colors.AccentAmber } else { $script:Colors.AccentBlue }
            break
        }
        '^(Display reset)' {
            $action = "Reset"; $color = $script:Colors.AccentAmber; break
        }
        '^(Standby|Clearing standby)' {
            $action = "Memory"; $color = $script:Colors.AccentBlue; break
        }
        '^(Quick Panel)' {
            $action = "QuickPanel"; $color = $script:Colors.AccentGreen; break
        }
        '^(Profiles refreshed|Profiles fallback|Profile refresh)' {
            $action = "Refresh"; $color = $script:Colors.AccentBlue; break
        }
        '^(Tray restart)' {
            $action = "Refresh"
            $color = if ($text -match '(?i)failed|warning') { $script:Colors.AccentAmber } else { $script:Colors.AccentBlue }
            break
        }
        '^(Opened backups|Open backups|No backups|Current backups)' {
            $action = "Backups"; $color = $script:Colors.AccentPurple; break
        }
        '^(Opened tray log|Open tray log)' {
            $action = "Log"; $color = $dimColor; break
        }
        '^(Opened tray settings|Open tray settings|Tray settings)' {
            $action = "Settings"; $color = $script:Colors.Text; break
        }
        '^(Opened installed runtime folder|Open runtime folder|Opened user profiles folder|Open profiles folder)' {
            $action = "Folder"; $color = $dimColor; break
        }
        '^(Toast popups)' {
            $action = "Toast"; $color = $script:Colors.AccentBlue; break
        }
        '^(Tray audio cues)' {
            $action = "Sound"; $color = $script:Colors.AccentBlue; break
        }
        '^(Profile missing|Profile not found|Apply timed out|Apply failed:|Not applied\.|Applied|Failed:|Error:)' {
            $action = "Apply"; $color = $script:Colors.AccentAmber; break
        }
        default {
            $action = $null
        }
    }

    if ([string]::IsNullOrWhiteSpace($action)) { return $null }
    return New-ActionBitmap -Action $action -Color $color
}

function New-TrayStatusBarImage {
    param(
        [AllowNull()][string]$PendingApplyText,
        [AllowNull()][string]$RebootPendingText,
        [AllowNull()][string]$VerificationProgressText,
        [AllowNull()][string]$ProfileId,
        [AllowNull()][string]$LastActionText,
        [AllowNull()][System.Drawing.Color]$FallbackColor
    )

    $dimColor = if ($FallbackColor) { $FallbackColor } else { $script:Colors.TextDim }
    if (-not [string]::IsNullOrWhiteSpace($PendingApplyText)) {
        return New-ActionBitmap -Action "PendingFix" -Color $script:Colors.AccentAmber
    }
    if (-not [string]::IsNullOrWhiteSpace($RebootPendingText)) {
        return New-ActionBitmap -Action "WindowsRestart" -Color $script:Colors.AccentAmber
    }
    $verificationBadge = -not [string]::IsNullOrWhiteSpace($VerificationProgressText)
    if (
        -not [string]::IsNullOrWhiteSpace($ProfileId) -and
        $script:Profiles -and
        $script:Profiles.Contains($ProfileId)
    ) {
        $favoriteBadge = (Test-Favorite -ProfileId $ProfileId -Config $script:TrayConfig)
        return New-TrayProfileMenuImage `
            -ProfileId $ProfileId `
            -IsActive ($ProfileId -eq $script:activeProfile) `
            -ShowSyncBadge $true `
            -FavoriteBadge $favoriteBadge
    }
    if (-not [string]::IsNullOrWhiteSpace($ProfileId)) {
        $profile = $null
        $category = "Other"
        $accent = Get-TrayProfileAccentColor -ProfileId $ProfileId -Profile $profile -Fallback $dimColor
        $gameGroup = Get-TrayProfileGameGroup -ProfileId $ProfileId -Profile $profile
        $modeBadge = if ("$ProfileId" -match '(?i)capture') {
            "capture"
        }
        elseif ("$ProfileId" -match '(?i)-hdr($|-)') {
            "hdr"
        }
        else {
            ""
        }
        $desc = Format-TrayDisplayCopy -Text $rawDesc
        $favoriteBadge = if (Get-Command Test-Favorite -ErrorAction SilentlyContinue) {
            Test-Favorite -ProfileId $ProfileId -Config $script:TrayConfig
        }
        else {
            $false
        }
        if ($ProfileId -eq $script:activeProfile -and (Get-Command New-ActiveGameBitmap -ErrorAction SilentlyContinue)) {
            return New-ActiveGameBitmap `
                -GameGroup $gameGroup `
                -Color $accent `
                -Category $category `
                -ModeBadge $modeBadge `
                -FavoriteBadge $favoriteBadge `
                -VerificationBadge $verificationBadge
        }
        if ($favoriteBadge -and (Get-Command New-FavoriteGameBitmap -ErrorAction SilentlyContinue)) {
            return New-FavoriteGameBitmap `
                -GameGroup $gameGroup `
                -Color $accent `
                -Category $category `
                -ModeBadge $modeBadge
        }
        if (Get-Command New-GameSyncBadgeBitmap -ErrorAction SilentlyContinue) {
            return New-GameSyncBadgeBitmap `
                -GameGroup $gameGroup `
                -Color $accent `
                -Category $category `
                -SyncMode "agnostic" `
                -ModeBadge $modeBadge
        }
    }
    if ($verificationBadge) {
        return New-ActionBitmap -Action "Search" -Color $script:Colors.AccentBlue
    }
    $lastActionImage = New-TrayLastActionStatusBitmap -LastActionText $LastActionText -FallbackColor $dimColor
    if ($lastActionImage) { return $lastActionImage }
    return New-ActionBitmap -Action "Info" -Color $dimColor
}

function Get-TrayProfileDisplayName {
    param([AllowNull()][string]$ProfileId)

    if ([string]::IsNullOrWhiteSpace($ProfileId)) { return "Profile not reported" }
    if ($script:Profiles -and $script:Profiles.Contains($ProfileId)) {
        $profile = $script:Profiles[$ProfileId]
        if ($profile -and -not [string]::IsNullOrWhiteSpace("$($profile.Name)")) {
            return (Format-TrayDisplayCopy -Text "$($profile.Name)")
        }
    }
    return (Format-TrayUserFacingText -Text $ProfileId)
}

function Get-TrayProfileObjectDisplayName {
    param(
        [AllowNull()][object]$Profile,
        [AllowNull()][string]$Fallback = ""
    )

    if ($Profile -and -not [string]::IsNullOrWhiteSpace("$($Profile.Name)")) {
        return (Format-TrayDisplayCopy -Text "$($Profile.Name)")
    }
    if (-not [string]::IsNullOrWhiteSpace($Fallback)) {
        return (Format-TrayUserFacingText -Text $Fallback)
    }
    return "computa"
}

function Get-ActiveTrayProfileRecord {
    $profileId = if ([string]::IsNullOrWhiteSpace([string]$script:activeProfile)) {
        $null
    }
    else {
        "$($script:activeProfile)"
    }

    $profile = $null
    $inCatalog = $false
    if ($profileId -and $script:Profiles -and $script:Profiles.Contains($profileId)) {
        $profile = $script:Profiles[$profileId]
        $inCatalog = ($null -ne $profile)
    }

    $displayName = if ($inCatalog -and $profile -and -not [string]::IsNullOrWhiteSpace("$($profile.Name)")) {
        Format-TrayDisplayCopy -Text "$($profile.Name)"
    }
    elseif ($profileId) {
        Format-TrayUserFacingText -Text $profileId
    }
    else {
        "No profile active"
    }

    return [pscustomobject]@{
        Id = $profileId
        Profile = $profile
        DisplayName = $displayName
        InCatalog = $inCatalog
    }
}

function Get-TrayProfileAccentColor {
    param(
        [AllowNull()][string]$ProfileId,
        [AllowNull()][object]$Profile,
        [System.Drawing.Color]$Fallback = [System.Drawing.Color]::White
    )

    if (-not $Profile -and -not [string]::IsNullOrWhiteSpace($ProfileId) -and $script:Profiles -and $script:Profiles.Contains($ProfileId)) {
        $Profile = $script:Profiles[$ProfileId]
    }

    $category = if ($Profile -and $Profile.Cat) { "$($Profile.Cat)" } else { "Other" }
    $baseColor = if (Get-Command Get-CategoryColor -ErrorAction SilentlyContinue) {
        Get-CategoryColor -Category $category -Fallback $Fallback
    }
    else {
        $Fallback
    }

    if (Get-Command Get-GameAccentColor -ErrorAction SilentlyContinue) {
        $gameGroup = Get-TrayProfileGameGroup -ProfileId $ProfileId -Profile $Profile
        return Get-GameAccentColor -GameGroup $gameGroup -FallbackColor $baseColor
    }

    return $baseColor
}

function Set-TrayStatusHeroImage {
    param(
        [AllowNull()][string]$ProfileId,
        [AllowNull()][object]$Profile,
        [switch]$ActiveBadge,
        [switch]$PendingApplyBadge,
        [switch]$WindowsRestartBadge,
        [switch]$VerificationBadge
    )

    if (-not $script:statusItem) { return }
    if ([string]::IsNullOrWhiteSpace($ProfileId)) {
        Set-MenuItemImageSafe -Item $script:statusItem -NewImage $null
        return
    }

    if (-not $Profile -and $script:Profiles -and $script:Profiles.Contains($ProfileId)) {
        $Profile = $script:Profiles[$ProfileId]
    }

    # If catalog metadata is stale, keep the status hero identifiable with the
    # same deterministic profile-id art used by toasts.
    $category = if ($Profile -and $Profile.Cat) { "$($Profile.Cat)" } else { "Other" }
    $accent = Get-TrayProfileAccentColor -ProfileId $ProfileId -Profile $Profile -Fallback $script:Colors.AccentGreen
    $gameGroup = Get-TrayProfileGameGroup -ProfileId $ProfileId -Profile $Profile
    $variant = if ($Profile -and $Profile.Variant) { "$($Profile.Variant)" } else { "" }
    $modeBadge = if ("$ProfileId" -match '(?i)capture' -or $variant -match '(?i)capture') {
        "capture"
    }
    elseif ($variant -match '(?i)\bHDR\b' -or "$ProfileId" -match '(?i)-hdr($|-)' ) {
        "hdr"
    }
    else {
        ""
    }
    $favoriteBadge = (Test-Favorite -ProfileId $ProfileId -Config $script:TrayConfig)
    $heroImage = if ($ActiveBadge -and (Get-Command New-ActiveGameBitmap -ErrorAction SilentlyContinue)) {
        New-ActiveGameBitmap `
            -GameGroup $gameGroup `
            -Color $accent `
            -Category $category `
            -ModeBadge $modeBadge `
            -FavoriteBadge $favoriteBadge `
            -PendingApplyBadge ([bool]$PendingApplyBadge) `
            -WindowsRestartBadge ([bool]$WindowsRestartBadge) `
            -VerificationBadge ([bool]$VerificationBadge)
    }
    elseif ($favoriteBadge -and (Get-Command New-FavoriteGameBitmap -ErrorAction SilentlyContinue)) {
        New-FavoriteGameBitmap `
            -GameGroup $gameGroup `
            -Color $accent `
            -Category $category `
            -SyncMode "agnostic" `
            -ModeBadge $modeBadge
    }
    elseif (-not [string]::IsNullOrWhiteSpace($modeBadge) -and (Get-Command New-GameSyncBadgeBitmap -ErrorAction SilentlyContinue)) {
        New-GameSyncBadgeBitmap `
            -GameGroup $gameGroup `
            -Color $accent `
            -Category $category `
            -SyncMode "agnostic" `
            -ModeBadge $modeBadge
    }
    elseif (Get-Command New-GameBitmap -ErrorAction SilentlyContinue) {
        New-GameBitmap -GameGroup $gameGroup -Color $accent -Category $category
    }
    else {
        $null
    }

    Set-MenuItemImageSafe -Item $script:statusItem -NewImage $heroImage
}

function Set-TrayActiveStatusItemFromState {
    if (-not $script:statusItem) { return }

    $activeRecord = Get-ActiveTrayProfileRecord
    if (-not $activeRecord.Id) {
        $script:statusItem.Text = "Ready|No profile active"
        $script:statusItem.ForeColor = $script:Colors.AccentGreen
        Set-TrayStatusHeroImage -ProfileId $null -Profile $null
        return
    }

    $profileDisplayName = if (
        $activeRecord.InCatalog -and
        $activeRecord.Profile -and
        -not [string]::IsNullOrWhiteSpace("$($activeRecord.Profile.Name)")
    ) {
        Format-TrayDisplayCopy -Text "$($activeRecord.Profile.Name)"
    }
    else {
        "$($activeRecord.DisplayName)"
    }
    $pendingApplyText = Get-ActiveProfilePendingApplyText
    $rebootPendingText = Get-ActiveProfileRebootPendingText
    $verificationProgressText = Get-ActiveProfileVerificationInProgressText
    if ($pendingApplyText) {
        $pendingStatusLabel = if ($script:ActiveProfileVerificationStatus -eq "mismatch") { "Profile mismatch" } else { "Pending profile fix" }
        $script:statusItem.Text = "$profileDisplayName|${pendingStatusLabel}: $pendingApplyText"
        $script:statusItem.ForeColor = $script:Colors.AccentAmber
        Set-TrayStatusHeroImage -ProfileId $activeRecord.Id -Profile $activeRecord.Profile -ActiveBadge -PendingApplyBadge
        return
    }
    if ($rebootPendingText) {
        $script:statusItem.Text = "$profileDisplayName|Windows restart required: $rebootPendingText"
        $script:statusItem.ForeColor = $script:Colors.AccentAmber
        Set-TrayStatusHeroImage -ProfileId $activeRecord.Id -Profile $activeRecord.Profile -ActiveBadge -WindowsRestartBadge
        return
    }
    if ($verificationProgressText) {
        $script:statusItem.Text = "$profileDisplayName|Checking profile state..."
        $script:statusItem.ForeColor = $script:Colors.AccentBlue
        Set-TrayStatusHeroImage -ProfileId $activeRecord.Id -Profile $activeRecord.Profile -ActiveBadge -VerificationBadge
        return
    }

    if (-not $activeRecord.InCatalog) {
        $script:statusItem.Text = "$($activeRecord.DisplayName)|Active profile not in current profile list"
        $script:statusItem.ForeColor = $script:Colors.AccentAmber
        Set-TrayStatusHeroImage -ProfileId $activeRecord.Id -Profile $null -ActiveBadge
        return
    }

    $p = $activeRecord.Profile
    $statusName = Get-TrayProfileObjectDisplayName -Profile $p -Fallback $activeRecord.Id
    $statusSub = Format-TrayDisplayCopy -Text "$($p.Sub)"
    $script:statusItem.Text = "$statusName|$statusSub"
    $script:statusItem.ForeColor = Get-TrayProfileAccentColor -ProfileId $activeRecord.Id -Profile $p -Fallback $script:Colors.AccentGreen
    Set-TrayStatusHeroImage -ProfileId $activeRecord.Id -Profile $p -ActiveBadge
}

function Get-QuickPanelEmptyStatus {
    $activeRecord = Get-ActiveTrayProfileRecord
    $favoriteIds = @(
        @($script:TrayConfig.favorites) |
            Where-Object { -not [string]::IsNullOrWhiteSpace("$_") } |
            ForEach-Object { "$_" }
    )

    $loadedFavoriteCount = 0
    foreach ($favId in $favoriteIds) {
        if ($script:Profiles -and $script:Profiles.Contains($favId)) {
            $loadedFavoriteCount++
        }
    }

    $activeMissing = ($activeRecord.Id -and -not $activeRecord.InCatalog)
    $favoritesMissing = ($favoriteIds.Count -gt 0 -and $loadedFavoriteCount -eq 0)

    if ($activeMissing -and $favoritesMissing) {
        return [pscustomobject]@{
            Message = "Active profile and favorites are not in the current profile list."
            LastAction = "Quick Panel empty: profile list mismatch"
            ProfileId = "$($activeRecord.Id)"
        }
    }
    if ($activeMissing) {
        return [pscustomobject]@{
            Message = "Active profile is not in the current profile list: $($activeRecord.DisplayName)."
            LastAction = "Quick Panel empty: active profile missing"
            ProfileId = "$($activeRecord.Id)"
        }
    }
    if ($favoritesMissing) {
        return [pscustomobject]@{
            Message = "Favorite profiles are not in the current profile list."
            LastAction = "Quick Panel empty: favorites missing"
            ProfileId = "$($favoriteIds[0])"
        }
    }

    return [pscustomobject]@{
        Message = "No active profile or favorites to show."
        LastAction = "Quick Panel empty"
        ProfileId = $null
    }
}

function Get-TrayProfilePreviewText {
    param(
        [string]$ProfileId,
        [object]$Profile
    )

    if (-not $Profile -and $script:Profiles -and $script:Profiles.Contains($ProfileId)) {
        $Profile = $script:Profiles[$ProfileId]
    }
    if (-not $Profile) { return "Preview: $(Format-TrayUserFacingText -Text $ProfileId)" }

    $parts = [System.Collections.Generic.List[string]]::new()
    $groupName = if (-not [string]::IsNullOrWhiteSpace("$($Profile.GroupName)")) {
        Format-TrayDisplayCopy -Text "$($Profile.GroupName)"
    }
    elseif (-not [string]::IsNullOrWhiteSpace("$($Profile.Name)")) {
        Format-TrayDisplayCopy -Text "$($Profile.Name)"
    }
    else {
        Format-TrayUserFacingText -Text $ProfileId
    }
    [void]$parts.Add("Preview: $groupName")

    if (-not [string]::IsNullOrWhiteSpace("$($Profile.Variant)")) {
        Add-UniqueTrayMessage -Target $parts -Message (Format-TrayDisplayCopy -Text "$($Profile.Variant)")
    }
    elseif (-not [string]::IsNullOrWhiteSpace("$($Profile.Cat)")) {
        Add-UniqueTrayMessage -Target $parts -Message (Format-TrayDisplayCopy -Text "$($Profile.Cat)")
    }

    if (-not [string]::IsNullOrWhiteSpace("$($Profile.SyncMode)")) {
        Add-UniqueTrayMessage -Target $parts -Message (Format-TrayDisplayCopy -Text "$($Profile.SyncMode)")
    }

    return (@($parts) -join "  |  ")
}

function Set-TrayProfileHoverPreview {
    param([string]$ProfileId)

    # Keep row hover layout-neutral. Native selection is enough feedback, and
    # rewriting hero/footer items makes WinForms recalculate the popup width.
    return
}

function Clear-TrayProfileHoverPreview {
    return
}

function Register-TrayProfileHoverPreview {
    param(
        [System.Windows.Forms.ToolStripMenuItem]$Item,
        [string]$ProfileId
    )

    if (-not $Item -or [string]::IsNullOrWhiteSpace($ProfileId)) { return }
    $capturedProfileId = $ProfileId
    $Item.Add_MouseEnter({
        Set-TrayProfileHoverPreview -ProfileId $capturedProfileId
    }.GetNewClosure())
    $Item.Add_MouseLeave({
        Clear-TrayProfileHoverPreview
    }.GetNewClosure())
}

function Get-RecentProfileTooltipText {
    param(
        [object]$Profile,
        [object]$Entry
    )

    $parts = [System.Collections.Generic.List[string]]::new()
    if ($Profile -and -not [string]::IsNullOrWhiteSpace("$($Profile.Sub)")) {
        [void]$parts.Add((Format-TrayDisplayCopy -Text "$($Profile.Sub)"))
    }
    if ($Entry) {
        $recordedAt = if ($Entry.PSObject.Properties["recorded_at"]) { $Entry.recorded_at } else { $null }
        $timestamp = if ($recordedAt) { $recordedAt } elseif ($Entry.PSObject.Properties["timestamp"]) { $Entry.timestamp } else { $null }
        $displayTime = Format-TrayTimestamp -Value $timestamp
        if ($displayTime -ne "time unknown") {
            [void]$parts.Add("Last applied: $displayTime")
        }
    }
    return (($parts | Where-Object { -not [string]::IsNullOrWhiteSpace("$_") }) -join "`n")
}

# ============================================================================
# ACTIONS
# ============================================================================

$script:AuditProc = $null
$script:AuditPollTimer = $null
$script:AuditOutputFile = $null
$script:AuditErrorFile = $null
$script:AuditStartedAt = $null

function Set-TrayAuditStatusItem {
    param(
        [string]$Text,
        [System.Drawing.Color]$Color,
        [string]$ChipText = "AUDIT",
        [switch]$IssueBadge
    )

    if (-not $script:auditStatusItem) { return }

    $script:auditStatusItem.Text = $Text
    $script:auditStatusItem.ForeColor = $Color
    $script:auditStatusItem.AccessibleName = "__status_bar__"
    $script:auditStatusItem.AccessibleDescription = if ([string]::IsNullOrWhiteSpace($ChipText)) { "AUDIT" } else { $ChipText }
    Set-MenuItemImageSafe -Item $script:auditStatusItem -NewImage (
        New-AuditStatusBitmap -Color $script:auditStatusItem.ForeColor -IssueBadge:$IssueBadge
    )
    $script:auditStatusItem.Visible = $true
}

function Test-AuditInFlight {
    if (-not $script:AuditProc) { return $false }
    try {
        return (-not $script:AuditProc.HasExited)
    }
    catch {
        return $false
    }
}

function Stop-AuditRuntime {
    param([switch]$KillProcess)

    if ($script:AuditPollTimer) {
        try { $script:AuditPollTimer.Stop() } catch {}
        try { $script:AuditPollTimer.Dispose() } catch {}
        $script:AuditPollTimer = $null
    }
    if ($script:AuditProc) {
        try {
            if ($KillProcess -and -not $script:AuditProc.HasExited) {
                $script:AuditProc.Kill()
            }
        } catch {}
        try { $script:AuditProc.Dispose() } catch {}
        $script:AuditProc = $null
    }
    foreach ($path in @($script:AuditOutputFile, $script:AuditErrorFile)) {
        if ($path) { Remove-Item $path -Force -ErrorAction SilentlyContinue }
    }
    $script:AuditOutputFile = $null
    $script:AuditErrorFile = $null
    $script:AuditStartedAt = $null
}

function Complete-AuditIfReady {
    $proc = $script:AuditProc
    if (-not $proc) {
        Stop-AuditRuntime
        return
    }

    $elapsedSeconds = if ($script:AuditStartedAt) {
        ([DateTime]::UtcNow - $script:AuditStartedAt).TotalSeconds
    }
    else {
        0
    }
    if (-not $proc.HasExited -and $elapsedSeconds -lt 60) {
        return
    }

    try {
        if ($script:AuditPollTimer) {
            $script:AuditPollTimer.Stop()
        }

        if (-not $proc.HasExited) {
            try { $proc.Kill() } catch {}
            throw "audit timed out after 60s"
        }

        $exitCode = $proc.ExitCode
        $rawOutput = Get-Content $script:AuditOutputFile -Raw -ErrorAction SilentlyContinue
        $errOutput = Get-Content $script:AuditErrorFile -Raw -ErrorAction SilentlyContinue
        if ($errOutput) { Write-TrayLog "Audit CLI stderr: $errOutput" -Level "WARN" }
        if ($null -ne $exitCode -and $exitCode -ne 0) {
            throw "audit exited $exitCode"
        }

        if (-not $rawOutput) {
            Show-Notification -Title "computa Audit" -Message "Audit failed: runtime returned no status" -Type "Error" -ActionName "Audit" -ActionColor $script:Colors.AccentBlue
            Set-IconState -State "Error"
            Set-TrayAuditStatusItem -Text "Audit Failed" -Color $script:Colors.AccentAmber -ChipText "AUDIT|FAIL" -IssueBadge
            $script:LastAction = "Audit failed: runtime returned no status"
            return
        }

        $json = Invoke-JsonSafe -Text $rawOutput -Source 'Audit'
        if ($null -eq $json) {
            Show-Notification -Title "computa Audit" -Message "Audit failed: runtime status unreadable" -Type "Error" -ActionName "Audit" -ActionColor $script:Colors.AccentBlue
            Set-IconState -State "Error"
            Set-TrayAuditStatusItem -Text "Audit Failed" -Color $script:Colors.AccentAmber -ChipText "AUDIT|FAIL" -IssueBadge
            $script:LastAction = "Audit failed: runtime status unreadable"
            return
        }
        if (-not $json.success -or -not $json.data) {
            $auditError = if ($json.error) { "$($json.error)" } else { "runtime status unreadable" }
            Show-Notification -Title "computa Audit" -Message "Audit failed: $auditError" -Type "Error" -ActionName "Audit" -ActionColor $script:Colors.AccentBlue
            Set-IconState -State "Error"
            Set-TrayAuditStatusItem -Text "Audit Failed" -Color $script:Colors.AccentAmber -ChipText "AUDIT|FAIL" -IssueBadge
            $script:LastAction = "Audit failed: $auditError"
            return
        }

        $issues = if ($json.data -is [System.Array]) { @($json.data) } else { @($json.data.issues) }
        $issueCount = if ($issues) { $issues.Count } else { 0 }
        $script:AuditIssueCount = $issueCount

        if ($issueCount -eq 0) {
            Show-Notification -Title "computa Audit" -Message "No issues detected by the current audit scope." -Type "Success" -ActionName "Audit" -ActionColor $script:Colors.AccentBlue
            $auditActionMessage = "Audit clean: no issues in scope"
            Set-IconState -State $(if ($script:activeProfile) { "Active" } else { "Idle" })
        }
        else {
            $auditIssueLabel = if ($issueCount -eq 1) { "issue" } else { "issues" }
            $auditStatusLabel = if ($issueCount -eq 1) { "Issue Found" } else { "Issues Found" }
            $issueIndex = 0
            foreach ($issue in @($issues)) {
                $issueIndex += 1
                $issueText = if ($issue -is [string]) {
                    "$issue"
                }
                elseif ($issue.message) {
                    if ($issue.details) { "$($issue.message): $($issue.details)" } else { "$($issue.message)" }
                }
                else {
                    try { $issue | ConvertTo-Json -Depth 5 -Compress } catch { "$issue" }
                }
                Write-TrayLog "Audit issue ${issueIndex}/${issueCount}: $(Format-TrayUserFacingText -Text $issueText)" -Level "WARN"
            }
            Show-Notification -Title "computa Audit" -Message "$issueCount $auditIssueLabel found. See tray log for details." -Type "Warning" -ActionName "Audit" -ActionColor $script:Colors.AccentBlue
            $auditActionMessage = "Audit ${auditIssueLabel} found: $issueCount"
            Set-IconState -State "Warning"
        }

        if ($script:auditStatusItem) {
            if ($issueCount -gt 0) {
                Set-TrayAuditStatusItem `
                    -Text "${auditStatusLabel}: $issueCount" `
                    -Color ([System.Drawing.Color]::FromArgb(255, 245, 184, 64)) `
                    -ChipText "AUDIT|ISSUES" `
                    -IssueBadge
            }
            else {
                Set-TrayAuditStatusItem -Text "No Issues In Scope" -Color $script:Colors.AccentGreen -ChipText "AUDIT|CLEAN"
            }
        }

        $script:LastAction = $auditActionMessage
    }
    catch {
        Write-TrayLog "Audit failed: $($_.Exception.Message)" -Level "ERROR"
        Show-Notification -Title "computa" -Message "Audit failed: $($_.Exception.Message)" -Type "Error" -ActionName "Audit" -ActionColor $script:Colors.AccentBlue
        Set-IconState -State "Error"
        Set-TrayAuditStatusItem -Text "Audit Failed" -Color $script:Colors.AccentAmber -ChipText "AUDIT|FAIL" -IssueBadge
        $script:LastAction = "Audit failed: $($_.Exception.Message)"
    }
    finally {
        $script:LastActionTime = Get-Date
        Stop-AuditRuntime
        Update-MenuState
    }
}

function Run-Audit {
    if (Test-AuditInFlight) {
        Show-Notification -Title "computa Audit" -Message "Audit is already running." -Type "Info" -ActionName "Audit" -ActionColor $script:Colors.AccentBlue
        Set-TrayLastAction -Message "Audit already running"
        Update-MenuState
        return
    }

    Write-TrayLog "Running audit..."
    Set-IconState -State "Applying"
    Set-TrayOperationTooltipText -Text "computa - Running Audit..."
    $script:LastAction = "Audit running"
    $script:LastActionTime = Get-Date
    Set-TrayAuditStatusItem -Text "Audit Running" -Color $script:Colors.AccentBlue -ChipText "AUDIT|RUN"
    Update-MenuState

    try {
        $script:AuditOutputFile = [System.IO.Path]::GetTempFileName()
        $script:AuditErrorFile = "$($script:AuditOutputFile).err"
        $script:AuditStartedAt = [DateTime]::UtcNow
        $script:AuditProc = Start-Process -FilePath $script:PythonExe -ArgumentList (Get-AbsoBackendArgs -CommandArgs @("audit", "--json")) `
            -NoNewWindow -PassThru -WorkingDirectory $script:ProjectRoot `
            -RedirectStandardOutput $script:AuditOutputFile -RedirectStandardError $script:AuditErrorFile
        # PS 5.1: cache the handle now or .ExitCode reads $null after exit.
        if ($script:AuditProc) { $null = $script:AuditProc.Handle }

        $pollTimer = New-Object System.Windows.Forms.Timer
        $pollTimer.Interval = 400
        $pollTimer.Add_Tick({ Complete-AuditIfReady })
        $script:AuditPollTimer = $pollTimer
        $pollTimer.Start()
    }
    catch {
        Write-TrayLog "Audit failed: $($_.Exception.Message)" -Level "ERROR"
        Show-Notification -Title "computa" -Message "Audit failed: $($_.Exception.Message)" -Type "Error" -ActionName "Audit" -ActionColor $script:Colors.AccentBlue
        Set-IconState -State "Error"
        Set-TrayAuditStatusItem -Text "Audit Failed" -Color $script:Colors.AccentAmber -ChipText "AUDIT|FAIL" -IssueBadge
        $script:LastAction = "Audit failed: $($_.Exception.Message)"
        $script:LastActionTime = Get-Date
        Stop-AuditRuntime -KillProcess
        Update-MenuState
    }
}

function Open-BackupsFolder {
    $backupsPath = Get-BackupPath
    if (Test-Path $backupsPath) {
        try {
            Start-Process "explorer.exe" -ArgumentList $backupsPath -ErrorAction Stop
            Set-TrayLastAction -Message "Opened backups folder"
            Update-MenuState
        }
        catch {
            Write-TrayLog "Failed to open backups folder: $($_.Exception.Message)" -Level "ERROR"
            Show-Notification -Title "computa" -Message "Failed to open backups folder: $($_.Exception.Message)" -Type "Error" -ActionName "Folder" -ActionColor $script:Colors.AccentPurple
            Set-TrayLastAction -Message "Open backups failed: $($_.Exception.Message)"
            Update-MenuState
        }
    }
    else {
        Show-Notification -Title "computa" -Message "Current backups folder not found. Applying a profile creates it." -Type "Info" -ActionName "Backups" -ActionColor $script:Colors.AccentPurple
        Set-TrayLastAction -Message "Current backups folder not found"
        Update-MenuState
    }
}

function Open-LogFile {
    try {
        if (-not (Test-Path $script:LogFile)) {
            Write-TrayLog "Tray log file created for manual view request"
        }
        Start-Process "notepad.exe" -ArgumentList $script:LogFile -ErrorAction Stop
        Set-TrayLastAction -Message "Opened tray log file"
        Update-MenuState
    }
    catch {
        Write-TrayLog "Failed to open tray log file: $($_.Exception.Message)" -Level "ERROR"
        Show-Notification -Title "computa" -Message "Failed to open tray log: $($_.Exception.Message)" -Type "Error" -ActionName "Log" -ActionColor $script:Colors.TextDim
        Set-TrayLastAction -Message "Open tray log failed: $($_.Exception.Message)"
        Update-MenuState
    }
}

function Get-TrayConfigDir {
    $appDataRoot = if ($env:APPDATA) {
        $env:APPDATA
    }
    else {
        [Environment]::GetFolderPath("ApplicationData")
    }
    return (Join-Path $appDataRoot "ABSO")
}

function Open-ConfigFolder {
    try {
        $configDir = Get-TrayConfigDir
        if (-not (Test-Path $configDir)) {
            New-Item -Path $configDir -ItemType Directory -Force | Out-Null
        }
        Start-Process "explorer.exe" -ArgumentList $configDir -ErrorAction Stop
        Set-TrayLastAction -Message "Opened tray settings folder"
        Update-MenuState
    }
    catch {
        Write-TrayLog "Failed to open tray settings folder: $($_.Exception.Message)" -Level "ERROR"
        Show-Notification -Title "computa" -Message "Failed to open tray settings folder: $($_.Exception.Message)" -Type "Error" -ActionName "Folder" -ActionColor $script:Colors.TextDim
        Set-TrayLastAction -Message "Open tray settings failed: $($_.Exception.Message)"
        Update-MenuState
    }
}

function Open-RuntimeFolder {
    try {
        $runtimeDir = Get-InstalledAppRoot
        if (-not (Test-Path $runtimeDir)) {
            New-Item -Path $runtimeDir -ItemType Directory -Force | Out-Null
        }
        Start-Process "explorer.exe" -ArgumentList $runtimeDir -ErrorAction Stop
        Set-TrayLastAction -Message "Opened installed runtime folder"
        Update-MenuState
    }
    catch {
        Write-TrayLog "Failed to open installed runtime folder: $($_.Exception.Message)" -Level "ERROR"
        Show-Notification -Title "computa" -Message "Failed to open runtime folder: $($_.Exception.Message)" -Type "Error" -ActionName "Folder" -ActionColor $script:Colors.TextDim
        Set-TrayLastAction -Message "Open runtime folder failed: $($_.Exception.Message)"
        Update-MenuState
    }
}

function Open-ProfilesFolder {
    try {
        $profilesDir = Join-Path $env:USERPROFILE ".abso\profiles"
        if (-not (Test-Path $profilesDir)) {
            New-Item -ItemType Directory -Path $profilesDir -Force | Out-Null
        }
        Start-Process "explorer.exe" -ArgumentList $profilesDir -ErrorAction Stop
        Set-TrayLastAction -Message "Opened user profiles folder"
        Update-MenuState
    }
    catch {
        Write-TrayLog "Failed to open user profiles folder: $($_.Exception.Message)" -Level "ERROR"
        Show-Notification -Title "computa" -Message "Failed to open profiles folder: $($_.Exception.Message)" -Type "Error" -ActionName "Folder" -ActionColor $script:Colors.TextDim
        Set-TrayLastAction -Message "Open profiles folder failed: $($_.Exception.Message)"
        Update-MenuState
    }
}

function Get-InstalledAppRoot {
    $localRoot = if ($env:LOCALAPPDATA) {
        $env:LOCALAPPDATA
    }
    else {
        Join-Path $env:USERPROFILE "AppData\Local"
    }
    return (Join-Path $localRoot "AdaptiveBattleStationOptimizer")
}

function Get-InstalledTrayDir {
    return (Join-Path (Get-InstalledAppRoot) "abso\tray")
}

function Test-StartupStringContainsLiteral {
    param(
        [string]$Text,
        [string]$Needle
    )

    if ([string]::IsNullOrWhiteSpace($Text) -or [string]::IsNullOrWhiteSpace($Needle)) {
        return $false
    }

    return ($Text.IndexOf($Needle, [System.StringComparison]::OrdinalIgnoreCase) -ge 0)
}

function Get-StartupStatusFallback {
    param([string]$InstallScript)

    $legacyShortcutPath = [System.IO.Path]::Combine(
        [Environment]::GetFolderPath("Startup"),
        "ABSO-Tray.lnk"
    )
    $trayDir = if (-not [string]::IsNullOrWhiteSpace($InstallScript)) {
        try { Split-Path -Parent $InstallScript } catch { $script:ScriptDir }
    }
    else {
        $script:ScriptDir
    }
    $expectedLauncherPath = Join-Path $trayDir "ABSO-StartupLaunch.ps1"
    $expectedVbsPath = Join-Path $trayDir "ABSO-Tray.vbs"
    $shortcutInstalled = Test-Path $legacyShortcutPath
    $taskName = "ABSO-Tray-Startup"
    $taskInstalled = $false
    $taskEnabled = $false
    $actionExecute = $null
    $actionArguments = $null
    $actionPathCurrent = $false

    $task = $null
    try {
        $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    }
    catch {
        Write-TrayLog "Startup fallback scheduled-task probe failed: $($_.Exception.Message)" -Level "WARN"
    }

    if ($task) {
        $taskInstalled = $true
        $taskEnabled = [bool]$task.Settings.Enabled
        $action = @($task.Actions) | Select-Object -First 1
        $actionExecute = if ($action) { "$($action.Execute)" } else { $null }
        $actionArguments = if ($action) { "$($action.Arguments)" } else { $null }
        $actionUsesLauncher = Test-StartupStringContainsLiteral -Text $actionArguments -Needle $expectedLauncherPath
        $actionUsesVbs = Test-StartupStringContainsLiteral -Text $actionArguments -Needle $expectedVbsPath
        $actionPathCurrent = [bool]($actionUsesLauncher -or $actionUsesVbs)
    }

    $taskUsable = ($taskInstalled -and $taskEnabled)
    $mode = if ($taskUsable) {
        "scheduled_task"
    }
    elseif ($shortcutInstalled) {
        "startup_shortcut"
    }
    else {
        "none"
    }

    return [PSCustomObject]@{
        installed                = ($taskUsable -or $shortcutInstalled)
        mode                     = $mode
        task_installed           = $taskInstalled
        task_enabled             = $taskEnabled
        task_action_execute      = $actionExecute
        task_action_arguments    = $actionArguments
        task_action_path_current = $actionPathCurrent
        shortcut_installed       = $shortcutInstalled
        task_name                = $taskName
        shortcut_path            = $legacyShortcutPath
        vbs_path                 = $expectedVbsPath
        launcher_path            = $expectedLauncherPath
    }
}

function Invoke-StartupInstallerJson {
    param(
        [string]$ScriptPath,
        [string[]]$CommandArgs,
        [int]$TimeoutSeconds = 30,
        [string]$Source = "StartupInstaller"
    )

    if ([string]::IsNullOrWhiteSpace($ScriptPath) -or -not (Test-Path $ScriptPath)) {
        throw "startup installer script not found"
    }

    $stdoutPath = [System.IO.Path]::GetTempFileName()
    $stderrPath = "$stdoutPath.err"
    $proc = $null
    try {
        $psArgs = @(
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-File", "`"$ScriptPath`""
        ) + @($CommandArgs)

        $proc = Start-Process -FilePath "powershell.exe" -ArgumentList $psArgs `
            -NoNewWindow -PassThru `
            -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
        # PS 5.1: cache the handle now or .ExitCode reads $null after the child
        # exits. This made every startup-status call fall back with
        # "empty/bad JSON or exit code " even though the installer succeeded.
        if ($proc) { $null = $proc.Handle }

        $timeoutMs = [Math]::Max(1, $TimeoutSeconds) * 1000
        $completed = $proc.WaitForExit($timeoutMs)
        if (-not $completed -or -not $proc.HasExited) {
            try { $proc.Kill() } catch {}
            throw "$Source timed out after ${TimeoutSeconds}s"
        }
        # Parameterless WaitForExit finalizes redirected output after the
        # timed wait so short reads cannot hand back a truncated payload.
        $proc.WaitForExit()

        $exitCode = $proc.ExitCode
        $raw = Get-Content $stdoutPath -Raw -ErrorAction SilentlyContinue
        $stderr = Get-Content $stderrPath -Raw -ErrorAction SilentlyContinue
        if ($stderr) { Write-TrayLog "$Source stderr: $stderr" -Level "WARN" }
        $payload = if ($raw) { Invoke-JsonSafe -Text $raw -Source $Source } else { $null }

        return [PSCustomObject]@{
            ExitCode = $exitCode
            Raw = $raw
            Payload = $payload
        }
    }
    finally {
        if ($proc) {
            try { if (-not $proc.HasExited) { $proc.Kill() } } catch {}
            try { $proc.Dispose() } catch {}
        }
        Remove-Item $stdoutPath -Force -ErrorAction SilentlyContinue
        Remove-Item $stderrPath -Force -ErrorAction SilentlyContinue
    }
}

function Get-StartupStatus {
    $installScript = Join-Path $script:ScriptDir "Install-Startup.ps1"

    if (-not (Test-Path $installScript)) {
        return (Get-StartupStatusFallback -InstallScript $installScript)
    }

    try {
        $result = Invoke-StartupInstallerJson -ScriptPath $installScript -CommandArgs @("-Status", "-Json") -TimeoutSeconds 15 -Source "StartupStatus"
        if (($result.ExitCode -eq 0 -or $null -eq $result.ExitCode) -and $result.Payload) {
            return $result.Payload
        }

        Write-TrayLog "Get-StartupStatus fallback: installer returned empty/bad JSON or exit code $($result.ExitCode)" -Level "WARN"
    }
    catch {
        Write-TrayLog "Get-StartupStatus failed: $($_.Exception.Message)" -Level "WARN"
    }

    return (Get-StartupStatusFallback -InstallScript $installScript)
}

function Get-InstalledStartupStatus {
    $installedScript = Join-Path (Get-InstalledTrayDir) "Install-Startup.ps1"
    if (-not (Test-Path $installedScript)) {
        return $null
    }

    try {
        $result = Invoke-StartupInstallerJson -ScriptPath $installedScript -CommandArgs @("-Status", "-Json") -TimeoutSeconds 15 -Source "InstalledStartupStatus"
        if (($result.ExitCode -eq 0 -or $null -eq $result.ExitCode) -and $result.Payload) {
            return $result.Payload
        }
        Write-TrayLog "Installed startup status check returned empty/bad JSON or exit code $($result.ExitCode)" -Level "WARN"
    }
    catch {
        Write-TrayLog "Installed startup status check failed: $($_.Exception.Message)" -Level "WARN"
    }

    return (Get-StartupStatusFallback -InstallScript $installedScript)
}

function Repair-StartupRegistration {
    param([switch]$Force)

    $installedScript = Join-Path (Get-InstalledTrayDir) "Install-Startup.ps1"
    if (-not (Test-Path $installedScript)) {
        Write-TrayLog "Startup repair skipped: installed startup script not found at $installedScript" -Level "WARN"
        return $false
    }

    $before = Get-InstalledStartupStatus
    if ((-not $Force) -and $before -and $before.task_action_path_current) {
        Write-TrayLog "Startup repair skipped: scheduled task already points at installed tray assets"
        return $true
    }

    try {
        $result = Invoke-StartupInstallerJson -ScriptPath $installedScript -CommandArgs @("-Install", "-Json") -TimeoutSeconds 120 -Source "StartupRepair"
        if ($null -ne $result.ExitCode -and $result.ExitCode -ne 0) {
            throw "Installer exit code $($result.ExitCode). Output: $($result.Raw)"
        }

        $after = Get-InstalledStartupStatus
        $repaired = [bool]($after -and $after.installed -and $after.task_action_path_current)
        if ($repaired) {
            Write-TrayLog "Startup repair completed: scheduled task now points at installed tray assets"
            try { Set-StartupMenuState -StartupStatus (Get-StartupStatus) } catch {}
            return $true
        }

        Write-TrayLog "Startup repair ran but task action is still not current" -Level "WARN"
        return $false
    }
    catch {
        Write-TrayLog "Startup repair failed: $($_.Exception.Message)" -Level "ERROR"
        return $false
    }
}

function Set-StartupMenuState {
    param([object]$StartupStatus)

    if (-not $script:startupItem) {
        return
    }

    $isInstalled = $false
    $mode = "none"
    $taskActionCurrent = $true

    if ($StartupStatus) {
        $isInstalled = [bool]$StartupStatus.installed
        if ($StartupStatus.mode) {
            $mode = "$($StartupStatus.mode)"
        }
        if (
            $StartupStatus.PSObject.Properties["task_action_path_current"] -and
            $StartupStatus.PSObject.Properties["task_installed"] -and
            [bool]$StartupStatus.task_installed
        ) {
            $taskActionCurrent = [bool]$StartupStatus.task_action_path_current
        }
    }

    $modeLabel = switch ($mode) {
        "scheduled_task" { "Task Scheduler" }
        "startup_shortcut" { "Startup Folder shortcut" }
        default { "not configured" }
    }

    $startupActionIsStale = ($isInstalled -and $mode -eq "scheduled_task" -and -not $taskActionCurrent)
    $startupIconAction = if ($startupActionIsStale) { "Warning" } else { "Startup" }
    $startupIconColor = if ($startupActionIsStale) { $script:Colors.AccentAmber } else { $script:Colors.Text }
    $startupChipText = if ($startupActionIsStale) { "STALE" } else { "STARTUP" }

    $script:startupItem.Text = if ($isInstalled) { "Disable Auto-Start" } else { "Enable Auto-Start" }
    $script:startupItem.ForeColor = if ($startupActionIsStale) { $script:Colors.AccentAmber } else { $script:Colors.Text }
    Set-MenuItemImageSafe -Item $script:startupItem -NewImage (New-ActionBitmap -Action $startupIconAction -Color $startupIconColor)
    $script:startupItem.Checked = $isInstalled
    $script:startupItem.ToolTipText = if ($isInstalled) {
        if ($mode -eq "scheduled_task" -and -not $taskActionCurrent) {
            "Auto-start task points at different tray files; toggle auto-start to rewrite it"
        }
        else {
            "Start computa Tray when Windows starts (configured via $modeLabel)"
        }
    }
    else {
        "Start computa Tray when Windows starts"
    }
    Set-TrayCommandItemVisualState -Item $script:startupItem -ChipText $startupChipText
}

function Toggle-Startup {
    $installScript = Join-Path $script:ScriptDir "Install-Startup.ps1"
    if (-not (Test-Path $installScript)) {
        Show-Notification -Title "computa" -Message "Startup installer not found" -Type "Error" -ActionName "Startup" -ActionColor $script:Colors.AccentAmber
        Write-TrayLog "Toggle-Startup failed: missing installer script at $installScript" -Level "ERROR"
        Set-TrayLastAction -Message "Startup update failed: installer not found"
        Update-MenuState
        return
    }

    $before = Get-StartupStatus
    $operation = if ($before.installed) { "-Uninstall" } else { "-Install" }

    Set-TrayOperationTooltipText -Text "computa - Updating startup..."
    Set-TrayLastAction -Message "Startup update running"
    Update-MenuState

    $installerWarning = ""
    try {
        $result = Invoke-StartupInstallerJson -ScriptPath $installScript -CommandArgs @($operation, "-Json") -TimeoutSeconds 120 -Source "Startup update"
        if ($null -ne $result.ExitCode -and $result.ExitCode -ne 0) {
            throw "Installer exit code $($result.ExitCode). Output: $($result.Raw)"
        }
        if ($result.Payload -and $result.Payload.PSObject.Properties["success"] -and -not [bool]$result.Payload.success) {
            $payloadError = if ($result.Payload.error) { "$($result.Payload.error)" } else { "installer reported failure" }
            throw $payloadError
        }
        if ($result.Payload -and $result.Payload.warning) {
            $installerWarning = "$($result.Payload.warning)"
        }
    }
    catch {
        Show-Notification -Title "computa" -Message "Startup update failed: $($_.Exception.Message)" -Type "Error" -ActionName "Startup" -ActionColor $script:Colors.AccentAmber
        Write-TrayLog "Toggle-Startup failed: $($_.Exception.Message)" -Level "ERROR"
        Set-TrayLastAction -Message "Startup update failed: $($_.Exception.Message)"
        Update-MenuState
        return
    }

    $after = Get-StartupStatus
    Set-StartupMenuState -StartupStatus $after

    if ((-not $before.installed) -and $after.installed) {
        $modeLabel = if ("$($after.mode)" -eq "scheduled_task") { "Task Scheduler" } else { "Startup Folder shortcut" }
        $startupMessage = if ([string]::IsNullOrWhiteSpace($installerWarning)) {
            "Added to Windows startup ($modeLabel)"
        }
        else {
            "Added to Windows startup ($modeLabel): $installerWarning"
        }
        $startupType = if ([string]::IsNullOrWhiteSpace($installerWarning)) { "Info" } else { "Warning" }
        Show-Notification -Title "computa" -Message $startupMessage -Type $startupType -ActionName "Startup" -ActionColor $script:Colors.AccentBlue
        Write-TrayLog "Startup enabled via mode: $($after.mode)"
        if ([string]::IsNullOrWhiteSpace($installerWarning)) {
            Set-TrayLastAction -Message "Startup enabled: $modeLabel"
        }
        else {
            Set-TrayLastAction -Message "Startup enabled with warning: $modeLabel"
        }
    }
    elseif ($before.installed -and (-not $after.installed)) {
        $startupMessage = if ([string]::IsNullOrWhiteSpace($installerWarning)) {
            "Removed from Windows startup"
        }
        else {
            "Removed from Windows startup: $installerWarning"
        }
        $startupType = if ([string]::IsNullOrWhiteSpace($installerWarning)) { "Info" } else { "Warning" }
        Show-Notification -Title "computa" -Message $startupMessage -Type $startupType -ActionName "Startup" -ActionColor $script:Colors.AccentBlue
        Write-TrayLog "Startup disabled"
        if ([string]::IsNullOrWhiteSpace($installerWarning)) {
            Set-TrayLastAction -Message "Startup disabled"
        }
        else {
            Set-TrayLastAction -Message "Startup disabled with warning"
        }
    }
    else {
        $state = if ($after.installed) { "enabled" } else { "disabled" }
        $unchangedMessage = if ([string]::IsNullOrWhiteSpace($installerWarning)) {
            "Startup unchanged; still $state"
        }
        else {
            "Startup unchanged; still ${state}: $installerWarning"
        }
        Show-Notification -Title "computa" -Message $unchangedMessage -Type "Warning" -ActionName "Startup" -ActionColor $script:Colors.AccentBlue
        Write-TrayLog "Toggle-Startup no state change detected (before=$($before.installed), after=$($after.installed))" -Level "WARN"
        Set-TrayLastAction -Message "Startup unchanged: $state"
    }
    Update-MenuState
}

function Get-BackupTimestamp {
    <#
    .SYNOPSIS
    Gets the logical backup creation time.

    Prefer manifest `created_at`, then the timestamp-style directory name.
    Filesystem CreationTime is only a fallback because copied/migrated backup
    directories get fresh filesystem timestamps.
    #>
    param([System.IO.DirectoryInfo]$Directory)

    if ($null -eq $Directory) {
        return Get-Date -Date "1970-01-01"
    }

    $manifest = Join-Path $Directory.FullName "manifest.json"
    if (Test-Path $manifest) {
        try {
            $mj = Get-Content $manifest -Raw -ErrorAction Stop | ConvertFrom-Json
            if ($mj.created_at) {
                return [DateTime]::Parse("$($mj.created_at)", [System.Globalization.CultureInfo]::InvariantCulture)
            }
        }
        catch {
            Write-TrayLog "Failed to read backup timestamp for '$($Directory.Name)': $($_.Exception.Message)" -Level "WARN"
        }
    }

    try {
        return [DateTime]::ParseExact($Directory.Name, "yyyy-MM-dd_HHmmss", [System.Globalization.CultureInfo]::InvariantCulture)
    }
    catch {
        return $Directory.CreationTime
    }
}

function Get-BackupPath {
    $roots = @(Get-BackupRoots)
    if ($roots.Count -gt 0) {
        return $roots[0].Path
    }
    return (Join-Path (Get-InstalledAppRoot) "backups")
}

function Get-BackupRoots {
    $roots = [System.Collections.Generic.List[object]]::new()
    $candidates = @(
        [PSCustomObject]@{ Role = "installed"; Path = (Join-Path (Get-InstalledAppRoot) "backups") },
        [PSCustomObject]@{ Role = "workspace"; Path = (Join-Path $script:ProjectRoot "backups") }
    )

    foreach ($candidate in $candidates) {
        if (
            $candidate.Path -and
            -not [string]::IsNullOrWhiteSpace("$($candidate.Path)") -and
            (Test-Path $candidate.Path)
        ) {
            [void]$roots.Add($candidate)
        }
    }

    return @($roots)
}

function Get-BackupDirectoryEntries {
    $entriesById = @{}
    foreach ($root in @(Get-BackupRoots)) {
        $dirs = Get-ChildItem $root.Path -Directory -ErrorAction SilentlyContinue
        foreach ($dir in @($dirs)) {
            if ($entriesById.ContainsKey($dir.Name)) { continue }
            $entriesById[$dir.Name] = [PSCustomObject]@{
                Directory = $dir
                Time = Get-BackupTimestamp -Directory $dir
                RootRole = $root.Role
                RootPath = $root.Path
            }
        }
    }

    return @($entriesById.Values)
}

function Get-BackupSourceLabel {
    param([AllowNull()][string]$Source)

    switch ("$Source") {
        "installed" { return "installed backup folder" }
        "workspace" { return "workspace backup folder" }
        default { return "backup location" }
    }
}

function Get-BackupSourceChipText {
    param([AllowNull()][string]$Source)

    switch ("$Source") {
        "installed" { return "INSTALLED" }
        "workspace" { return "WORKSPACE" }
        default { return "BACKUP" }
    }
}

function Get-BackupMenuChipText {
    param([int]$VisibleBackupCount)

    $count = [Math]::Max(0, $VisibleBackupCount)
    if ($count -le 0) { return "NO BACKUPS" }
    if ($count -eq 1) { return "1 BACKUP" }
    return "$count BACKUPS"
}

function Get-LastBackupTime {
    $latest = Get-BackupDirectoryEntries |
        Sort-Object Time -Descending |
        Select-Object -First 1
    if ($latest) {
        $age = (Get-Date) - $latest.Time
        if ($age.TotalSeconds -lt 0) { return "just now" }
        if ($age.TotalMinutes -lt 60) { return "$([int]$age.TotalMinutes)m ago" }
        elseif ($age.TotalHours -lt 24) { return "$([int]$age.TotalHours)h ago" }
        else { return "$([int]$age.TotalDays)d ago" }
    }
    return "Never"
}

function Get-RecentBackups {
    <#
    .SYNOPSIS
    Gets the last N backup folders with metadata.
    #>
    param([int]$Count = 5)

    $result = @()
    $dirs = Get-BackupDirectoryEntries |
        Sort-Object Time -Descending |
        Select-Object -First $Count
    foreach ($entry in $dirs) {
        $dir = $entry.Directory
        $timestamp = $entry.Time
        $manifest = Join-Path $dir.FullName "manifest.json"
        $label = $dir.Name
        $profileId = $null
        if (Test-Path $manifest) {
            try {
                $mj = Get-Content $manifest -Raw | ConvertFrom-Json
                $displayTime = Format-TrayTimestamp -Value $timestamp
                if ($mj.profile_id) {
                    $profileId = "$($mj.profile_id)"
                    $profileName = Get-TrayProfileDisplayName -ProfileId $profileId
                    $label = "$profileName - $displayTime"
                }
                else { $label = $displayTime }
            } catch {
                $label = Format-TrayTimestamp -Value $timestamp
            }
        }
        $result += @{
            Path = $dir.FullName
            Name = $dir.Name
            Label = $label
            ProfileId = $profileId
            Time = $timestamp
            Source = $entry.RootRole
            SourceLabel = Get-BackupSourceLabel -Source $entry.RootRole
            RootPath = $entry.RootPath
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
        $searchText = "$id $($p.Name) $($p.GroupName) $($p.Variant) $($p.Sub) $($p.Cat) $($p.Desc)".ToLower()

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

function Get-TraySearchResultGameGroups {
    param(
        [object[]]$MatchedIds,
        [int]$Count = 3
    )

    $groups = [System.Collections.Generic.List[string]]::new()
    $seen = @{}
    foreach ($id in @($MatchedIds)) {
        if ([string]::IsNullOrWhiteSpace("$id")) { continue }
        if (-not $script:Profiles -or -not $script:Profiles.Contains($id)) { continue }
        $profile = $script:Profiles[$id]
        $gameGroup = Get-TrayProfileGameGroup -ProfileId "$id" -Profile $profile
        if ([string]::IsNullOrWhiteSpace($gameGroup)) { continue }
        $key = "$gameGroup".Trim().ToLowerInvariant()
        if ($seen.ContainsKey($key)) { continue }
        $seen[$key] = $true
        [void]$groups.Add("$gameGroup")
        if ($groups.Count -ge $Count) { break }
    }
    return @($groups)
}

function Set-TraySearchStatus {
    param(
        [string]$Query,
        [object[]]$MatchedIds
    )

    if (-not $script:searchStatusItem) { return }

    $fullQuery = "$Query".Trim()
    if ([string]::IsNullOrWhiteSpace($fullQuery)) {
        $script:searchStatusItem.Visible = $false
        $script:searchStatusItem.AccessibleDescription = ""
        return
    }
    $cleanQuery = $fullQuery
    if ($cleanQuery.Length -gt 28) {
        $cleanQuery = $cleanQuery.Substring(0, 28) + "..."
    }

    $matchCount = @($MatchedIds).Count
    $plural = if ($matchCount -eq 1) { "match" } else { "matches" }
    if ($matchCount -eq 0) {
        $script:searchStatusItem.Text = "SEARCH: no matches | $cleanQuery"
        $script:searchStatusItem.ForeColor = $script:Colors.AccentAmber
        $script:searchStatusItem.ToolTipText = "No profile matches: $fullQuery"
        $script:searchStatusItem.AccessibleDescription = "SEARCH|NONE"
        Set-MenuItemImageSafe -Item $script:searchStatusItem -NewImage (New-ActionBitmap -Action "Search" -Color $script:Colors.AccentAmber)
    }
    else {
        $script:searchStatusItem.Text = "SEARCH: $matchCount $plural | $cleanQuery"
        $script:searchStatusItem.ForeColor = $script:Colors.AccentGold
        $tooltipCount = if ($matchCount -eq 1) { "1 profile match" } else { "$matchCount profile matches" }
        $script:searchStatusItem.ToolTipText = "${tooltipCount}: $fullQuery"
        $script:searchStatusItem.AccessibleDescription = if ($matchCount -eq 1) { "SEARCH|MATCH" } else { "SEARCH|MATCHES" }
        $matchedGameGroups = Get-TraySearchResultGameGroups -MatchedIds $MatchedIds -Count 3
        if ($matchedGameGroups.Count -gt 0 -and (Get-Command New-GameMosaicBitmap -ErrorAction SilentlyContinue)) {
            Set-MenuItemImageSafe -Item $script:searchStatusItem -NewImage (
                New-GameMosaicBitmap -GameGroups $matchedGameGroups -Color $script:Colors.AccentGold -Category "Other"
            )
        }
        else {
            Set-MenuItemImageSafe -Item $script:searchStatusItem -NewImage (New-ActionBitmap -Action "Search" -Color $script:Colors.AccentGold)
        }
    }
    $script:searchStatusItem.Visible = $true
}

# ============================================================================
# PROCESS GUARD — Demote misbehaving background apps from RealTime priority
# ============================================================================

# Default targets: Discord sets itself to RealTime which starves game threads.
# Process names are queried in a single Get-Process call for efficiency.
$script:ProcessGuardNames = @("Discord", "DiscordPTB", "DiscordCanary")
$script:ProcessGuardCeiling = [System.Diagnostics.ProcessPriorityClass]::Normal
$script:ProcessGuardDemotedPIDs = @{}  # PID -> $true; suppresses repeat log spam
$script:ProcessGuardIdleIntervalMs  = 30000  # 30s when no targets found
$script:ProcessGuardActiveIntervalMs = 5000  # 5s after a demotion (re-escalation window)
$script:ProcessGuardIntervalMs = $script:ProcessGuardIdleIntervalMs

function Invoke-ProcessGuardTick {
    <#
    .SYNOPSIS
    Single Get-Process call for all guard targets. Demotes any above the ceiling.
    Adaptive interval: speeds up after demotion, slows down when idle.
    #>
    $demotedThisTick = $false

    # One call, all names — returns $null when none match
    $procs = Get-Process -Name $script:ProcessGuardNames -ErrorAction SilentlyContinue
    if (-not $procs) {
        # Nothing running — switch to slow poll and clear stale PID cache
        if ($script:ProcessGuardDemotedPIDs.Count -gt 0) { $script:ProcessGuardDemotedPIDs = @{} }
        if ($script:ProcessGuardTimer -and $script:ProcessGuardTimer.Interval -ne $script:ProcessGuardIdleIntervalMs) {
            $script:ProcessGuardTimer.Interval = $script:ProcessGuardIdleIntervalMs
        }
        return
    }

    foreach ($proc in @($procs)) {
        try {
            if ($proc.PriorityClass -gt $script:ProcessGuardCeiling) {
                $was = $proc.PriorityClass
                $proc.PriorityClass = $script:ProcessGuardCeiling
                $demotedThisTick = $true

                # Log first demotion per PID only
                $pidKey = $proc.Id
                if (-not $script:ProcessGuardDemotedPIDs.ContainsKey($pidKey)) {
                    $script:ProcessGuardDemotedPIDs[$pidKey] = $true
                    Write-TrayLog "ProcessGuard: Demoted $($proc.ProcessName) (PID $pidKey) from $was to $($script:ProcessGuardCeiling)"
                }
            }
        } catch {
            # Process exited or access denied between enumerate and set — benign
        } finally {
            if ($proc -and $proc -is [System.IDisposable]) {
                try { $proc.Dispose() } catch {}
            }
        }
    }

    # Adaptive interval: fast poll after demotion, slow poll when stable
    $desiredInterval = if ($demotedThisTick) { $script:ProcessGuardActiveIntervalMs } else { $script:ProcessGuardIdleIntervalMs }
    if ($script:ProcessGuardTimer -and $script:ProcessGuardTimer.Interval -ne $desiredInterval) {
        $script:ProcessGuardTimer.Interval = $desiredInterval
    }
}

function Start-ProcessGuardTimer {
    <#
    .SYNOPSIS
    Starts the periodic process guard timer.
    #>
    if ($script:ProcessGuardTimer) {
        try { $script:ProcessGuardTimer.Stop() } catch {}
        try { $script:ProcessGuardTimer.Dispose() } catch {}
    }

    $script:ProcessGuardTimer = New-Object System.Windows.Forms.Timer
    $script:ProcessGuardTimer.Interval = $script:ProcessGuardIdleIntervalMs
    $script:ProcessGuardTimer.Add_Tick({
        try { Invoke-ProcessGuardTick } catch {
            try { Write-TrayLog "ProcessGuard tick error: $($_.Exception.Message)" -Level "WARN" } catch {}
        }
    })
    $script:ProcessGuardTimer.Start()
    Write-TrayLog "ProcessGuard started (idle: $($script:ProcessGuardIdleIntervalMs)ms, active: $($script:ProcessGuardActiveIntervalMs)ms, targets: $($script:ProcessGuardNames -join ', '))"

    # Run once immediately so startup-launched Discord gets caught right away
    try { Invoke-ProcessGuardTick } catch {}
}

function Stop-ProcessGuardTimer {
    if ($script:ProcessGuardTimer) {
        try { $script:ProcessGuardTimer.Stop() } catch {}
        try { $script:ProcessGuardTimer.Dispose() } catch {}
        $script:ProcessGuardTimer = $null
    }
}

# ============================================================================
# LAUNCH SANITIZER - Kill latency-impacting overlays/capture/sync daemons
# whenever the active profile's game binary is detected running.
# ============================================================================
#
# Where ProcessGuard demotes Discord priority continuously, LaunchSanitizer
# only fires while the active profile's game is alive. It calls the Python
# CLI `launch-sweep` against the per-profile killset (overlays, RTSS, Medal,
# Xbox Game Bar, audio-enhancer DPC offenders) so anything that wakes up or
# respawns mid-session is caught without the user having to babysit.
#
# Sweep tier:
#   - always-safe: applied automatically (overlays/capture/OSDs/DPC offenders)
#   - opt-in:      cloud sync + OEM RGB. Off unless TrayConfig flag is true.
#
# Cadence:
#   - idle (no game alive): 30s tick to keep tray overhead near zero
#   - active (game alive):  10s tick to catch respawns quickly
#
# Per-profile launch killset comes from $script:Profiles[<id>].KillsetAlwaysSafe
# which is populated by the catalog cache - no game-specific lists live in the
# tray itself.

$script:LaunchSanitizerIdleIntervalMs   = 30000
$script:LaunchSanitizerActiveIntervalMs = 10000
$script:LaunchSanitizerTimer = $null
$script:LaunchSanitizerActiveProfileId = $null
$script:LaunchSanitizerLastSweepStopped = @{}
$script:LaunchSanitizerGameWasAlive = $false
$script:LaunchSanitizerSweepProc = $null
$script:LaunchSanitizerSweepPollTimer = $null
$script:LaunchSanitizerSweepOutputFile = $null
$script:LaunchSanitizerSweepErrorFile = $null
$script:LaunchSanitizerSweepProfileId = $null
$script:LaunchSanitizerSweepFirstDetection = $false
$script:LaunchSanitizerSweepStartedAt = $null

# --- Keep-Awake (anti-sleep) for gamepad-driven sessions --------------------
# SetThreadExecutionState inhibits system + display idle sleep for the lifetime
# of the asserting thread. The WinForms timer tick runs on the tray UI thread,
# which lives the whole session, so an ES_CONTINUOUS assertion holds until we
# clear it. Ephemeral and self-reverting: no powercfg edits, no backup/restore,
# and zero interaction with the display/GPU pipeline. Asserted only for profiles
# whose catalog flag KeepAwakeWhileGaming is true (emulators) while their game
# is alive; cleared on game exit, profile change, and tray shutdown.
if (-not ('ABSO.PowerState' -as [type])) {
    Add-Type -Namespace 'ABSO' -Name 'PowerState' -MemberDefinition @'
[System.Runtime.InteropServices.DllImport("kernel32.dll", SetLastError = true)]
public static extern uint SetThreadExecutionState(uint esFlags);
'@
}
$script:KeepAwakeAsserted   = $false
$script:ES_CONTINUOUS       = [uint32]0x80000000
$script:ES_SYSTEM_REQUIRED  = [uint32]0x00000001
$script:ES_DISPLAY_REQUIRED = [uint32]0x00000002

function Set-AbsoKeepAwake {
    try {
        $flags = [uint32]($script:ES_CONTINUOUS -bor $script:ES_SYSTEM_REQUIRED -bor $script:ES_DISPLAY_REQUIRED)
        [ABSO.PowerState]::SetThreadExecutionState($flags) | Out-Null
        if (-not $script:KeepAwakeAsserted) {
            Write-TrayLog "KeepAwake: inhibiting system/display sleep for active game session"
        }
        $script:KeepAwakeAsserted = $true
    }
    catch {
        Write-TrayLog "KeepAwake: assert failed: $($_.Exception.Message)" -Level "WARN"
    }
}

function Clear-AbsoKeepAwake {
    if (-not $script:KeepAwakeAsserted) { return }
    try {
        [ABSO.PowerState]::SetThreadExecutionState($script:ES_CONTINUOUS) | Out-Null
        Write-TrayLog "KeepAwake: released sleep inhibitor"
    }
    catch {}
    $script:KeepAwakeAsserted = $false
}

# --- ProBalance governor (background CPU-contention restraint) --------------
# Runs the backend `cpu-balance --pid <game> --stop-file <f>` daemon for the
# session. It demotes only background CPU spikers (never the game, foreground,
# anti-cheat, launchers, audio, or process_overrides.protect images) and
# auto-restores them. Gated on the tray-config `cpuBalancer` flag (default OFF;
# opt in per machine). Stopped via the stop-file sentinel so the daemon's
# cleanup restores every demoted priority — never a hard kill except as a last
# resort.
$script:CpuBalancerProc      = $null
$script:CpuBalancerStopFile  = $null
$script:CpuBalancerProfileId = $null
$script:CpuBalancerGamePid   = $null

function Test-CpuBalancerRunning {
    if (-not $script:CpuBalancerProc) { return $false }
    try { return (-not $script:CpuBalancerProc.HasExited) } catch { return $false }
}

function Get-ActiveProfileGamePid {
    <#
    .SYNOPSIS
    Returns the PID of the first running game executable for the active profile,
    or $null. Used to scope the ProBalance governor to the live game.
    #>
    $summary = Get-ActiveProfileKillsetSummary
    if (-not $summary -or -not $summary.Exes -or $summary.Exes.Count -eq 0) { return $null }
    $baseNames = @()
    foreach ($exe in $summary.Exes) {
        if ([string]::IsNullOrWhiteSpace("$exe")) { continue }
        $name = "$exe"
        if ($name.ToLowerInvariant().EndsWith(".exe")) {
            $name = $name.Substring(0, $name.Length - 4)
        }
        $baseNames += $name
    }
    if ($baseNames.Count -eq 0) { return $null }

    $procs = Get-Process -Name $baseNames -ErrorAction SilentlyContinue
    if (-not $procs) { return $null }
    $gamePid = $null
    foreach ($p in @($procs)) {
        if ($null -eq $gamePid) { $gamePid = $p.Id }
        try { $p.Dispose() } catch {}
    }
    return $gamePid
}

function Start-CpuBalancerForGame {
    param(
        [Parameter(Mandatory = $true)][string]$ProfileId,
        [Parameter(Mandatory = $true)][int]$GamePid
    )

    if (Test-CpuBalancerRunning) { return $false }
    if (-not $script:PythonExe) {
        Write-TrayLog "CpuBalancer: PythonExe unresolved; skipping" -Level "WARN"
        return $false
    }

    try {
        # GetTempFileName creates the file; the balancer treats EXISTENCE as the
        # stop signal, so delete it now and only re-create it to request stop.
        $script:CpuBalancerStopFile = [System.IO.Path]::GetTempFileName()
        Remove-Item $script:CpuBalancerStopFile -Force -ErrorAction SilentlyContinue

        $cmdArgs = @("cpu-balance", "--pid", "$GamePid", "--stop-file", $script:CpuBalancerStopFile)
        # Tier B opt-ins (default OFF), passed through as CLI flags so the daemon
        # also performs P-core steering / EcoQoS herding / watchdog rules.
        if ($script:TrayConfig -and [bool]$script:TrayConfig.cpuSets) { $cmdArgs += "--cpu-sets" }
        if ($script:TrayConfig -and [bool]$script:TrayConfig.ecoMode) { $cmdArgs += "--eco" }
        if ($script:TrayConfig -and [bool]$script:TrayConfig.watchdog) {
            $cmdArgs += "--watchdog"
            # Restrict the watchdog to demote-only for online/ranked profiles.
            $wdProfile = $script:Profiles[$ProfileId]
            if ($wdProfile -and [bool]$wdProfile.IsOnline) { $cmdArgs += "--online" }
        }
        $arguments = Get-AbsoBackendArgs -CommandArgs $cmdArgs
        $script:CpuBalancerProc = Start-Process -FilePath $script:PythonExe `
            -ArgumentList $arguments `
            -NoNewWindow -PassThru -WorkingDirectory $script:ProjectRoot
        $script:CpuBalancerProfileId = $ProfileId
        $script:CpuBalancerGamePid = $GamePid
        Write-TrayLog "CpuBalancer: started for '$ProfileId' (game pid $GamePid)"
        return $true
    }
    catch {
        Write-TrayLog "CpuBalancer: failed to start: $($_.Exception.Message)" -Level "WARN"
        Stop-CpuBalancerForGame
        return $false
    }
}

function Stop-CpuBalancerForGame {
    <#
    .SYNOPSIS
    Graceful stop: drop the stop-file sentinel so the daemon's finally-block
    restores every demoted priority, wait briefly, then reap. Hard-kill only as
    a last resort. Idempotent / safe when nothing is running.
    #>
    if ($script:CpuBalancerStopFile) {
        try { New-Item -ItemType File -Path $script:CpuBalancerStopFile -Force | Out-Null } catch {}
    }
    if ($script:CpuBalancerProc) {
        try {
            if (-not $script:CpuBalancerProc.HasExited) {
                # Balancer polls the sentinel ~1/s; this brief wait happens only
                # on game-exit / profile-change / shutdown (rare events).
                $null = $script:CpuBalancerProc.WaitForExit(3000)
                if (-not $script:CpuBalancerProc.HasExited) {
                    Write-TrayLog "CpuBalancer: graceful stop timed out; killing" -Level "WARN"
                    try { $script:CpuBalancerProc.Kill() } catch {}
                }
            }
        }
        catch {}
        try { $script:CpuBalancerProc.Dispose() } catch {}
        $script:CpuBalancerProc = $null
    }
    if ($script:CpuBalancerStopFile) {
        Remove-Item $script:CpuBalancerStopFile -Force -ErrorAction SilentlyContinue
        $script:CpuBalancerStopFile = $null
    }
    $script:CpuBalancerProfileId = $null
    $script:CpuBalancerGamePid = $null
}

function Get-ActiveProfileKillsetSummary {
    <#
    .SYNOPSIS
    Returns a quick summary of the launch killset for the currently active profile.
    Used by the QuickPanel / log on startup so the user can confirm the wiring
    survived a profile cache regeneration.
    #>
    $profileId = $script:activeProfile
    if ([string]::IsNullOrWhiteSpace($profileId)) { return $null }
    $profile = $script:Profiles[$profileId]
    if (-not $profile) { return $null }
    return [pscustomobject]@{
        ProfileId    = $profileId
        Exes         = @($profile.Exes)
        AlwaysSafe   = @($profile.KillsetAlwaysSafe)
        OptIn        = @($profile.KillsetOptIn)
        StrictPath   = [bool]$profile.RequiresOverlayFree
    }
}

function Test-IsActiveProfileGameRunning {
    <#
    .SYNOPSIS
    Returns $true if any of the active profile's game executables are alive.
    Strips .exe before calling Get-Process because Get-Process matches by
    base name (no extension).
    #>
    $summary = Get-ActiveProfileKillsetSummary
    if (-not $summary -or -not $summary.Exes -or $summary.Exes.Count -eq 0) {
        return $false
    }
    $baseNames = @()
    foreach ($exe in $summary.Exes) {
        if ([string]::IsNullOrWhiteSpace("$exe")) { continue }
        $name = "$exe"
        if ($name.ToLowerInvariant().EndsWith(".exe")) {
            $name = $name.Substring(0, $name.Length - 4)
        }
        $baseNames += $name
    }
    if ($baseNames.Count -eq 0) { return $false }

    $procs = Get-Process -Name $baseNames -ErrorAction SilentlyContinue
    if ($procs) {
        # Dispose handles right away - PS holds them open otherwise
        foreach ($p in @($procs)) {
            try { $p.Dispose() } catch {}
        }
        return $true
    }
    return $false
}

function Test-LaunchSweepInFlight {
    if (-not $script:LaunchSanitizerSweepProc) { return $false }
    try {
        return (-not $script:LaunchSanitizerSweepProc.HasExited)
    }
    catch {
        return $false
    }
}

function Stop-LaunchSweepRuntime {
    param([switch]$KillProcess)

    if ($script:LaunchSanitizerSweepPollTimer) {
        try { $script:LaunchSanitizerSweepPollTimer.Stop() } catch {}
        try { $script:LaunchSanitizerSweepPollTimer.Dispose() } catch {}
        $script:LaunchSanitizerSweepPollTimer = $null
    }

    if ($script:LaunchSanitizerSweepProc) {
        try {
            if ($KillProcess -and -not $script:LaunchSanitizerSweepProc.HasExited) {
                $script:LaunchSanitizerSweepProc.Kill()
            }
        } catch {}
        try { $script:LaunchSanitizerSweepProc.Dispose() } catch {}
        $script:LaunchSanitizerSweepProc = $null
    }

    foreach ($path in @($script:LaunchSanitizerSweepOutputFile, $script:LaunchSanitizerSweepErrorFile)) {
        if ($path) { Remove-Item $path -Force -ErrorAction SilentlyContinue }
    }
    $script:LaunchSanitizerSweepOutputFile = $null
    $script:LaunchSanitizerSweepErrorFile = $null
    $script:LaunchSanitizerSweepProfileId = $null
    $script:LaunchSanitizerSweepFirstDetection = $false
    $script:LaunchSanitizerSweepStartedAt = $null
}

function Apply-LaunchSweepPayload {
    param(
        [AllowNull()][object]$Payload,
        [string]$ProfileId,
        [bool]$IsFirstDetection
    )

    if (-not $Payload -or -not $Payload.result) { return }

    $stopped = @()
    if ($Payload.result.stopped) { $stopped = @($Payload.result.stopped) }

    foreach ($img in $stopped) {
        if (-not $script:LaunchSanitizerLastSweepStopped.ContainsKey("$img")) {
            $script:LaunchSanitizerLastSweepStopped["$img"] = $true
            Write-TrayLog "LaunchSanitizer: stopped $img during '$ProfileId' session"
        }
    }

    if ($Payload.result.warnings) {
        foreach ($warning in @($Payload.result.warnings)) {
            Write-TrayLog "LaunchSanitizer warning: $warning" -Level "WARN"
        }
    }

    # Surface a single toast on the FIRST sweep that actually stops
    # something, so the user knows the launch sanitizer did its job.
    # Subsequent ticks (e.g. Medal respawn) stay quiet in the log.
    if ($IsFirstDetection -and $stopped.Count -gt 0) {
        $summary = $stopped -join ", "
        if ($summary.Length -gt 80) {
            $summary = $summary.Substring(0, 80) + "..."
        }
        try {
            $sanitizerProfile = $null
            if (-not [string]::IsNullOrWhiteSpace($ProfileId) -and $script:Profiles -and $script:Profiles.Contains($ProfileId)) {
                $sanitizerProfile = $script:Profiles[$ProfileId]
            }
            $sanitizerVisual = Get-TrayProfileToastVisualArgs -ProfileId $ProfileId -Profile $sanitizerProfile -ActiveBadge
            $sanitizerTitle = if ($sanitizerProfile) {
                Get-TrayProfileDisplayName -ProfileId $ProfileId
            }
            else {
                "computa Launch Sanitizer"
            }
            Show-Notification @sanitizerVisual -Title $sanitizerTitle `
                -Message "Launch sanitizer stopped: $summary" `
                -Type "Success" `
                -MetaText $ProfileId
        } catch {
            Write-TrayLog "LaunchSanitizer: notification failed: $($_.Exception.Message)" -Level "WARN"
        }
    }
}

function Complete-LaunchSweepIfReady {
    $proc = $script:LaunchSanitizerSweepProc
    if (-not $proc) {
        Stop-LaunchSweepRuntime
        return
    }

    $elapsedSeconds = if ($script:LaunchSanitizerSweepStartedAt) {
        ([DateTime]::UtcNow - $script:LaunchSanitizerSweepStartedAt).TotalSeconds
    }
    else {
        0
    }
    if (-not $proc.HasExited -and $elapsedSeconds -lt 30) {
        return
    }

    try {
        if ($script:LaunchSanitizerSweepPollTimer) {
            $script:LaunchSanitizerSweepPollTimer.Stop()
        }

        if (-not $proc.HasExited) {
            try { $proc.Kill() } catch {}
            throw "launch-sweep timed out after 30s"
        }

        $exitCode = $proc.ExitCode
        $stdout = Get-Content $script:LaunchSanitizerSweepOutputFile -Raw -ErrorAction SilentlyContinue
        $stderr = Get-Content $script:LaunchSanitizerSweepErrorFile -Raw -ErrorAction SilentlyContinue
        if ($stderr) {
            Write-TrayLog "LaunchSanitizer stderr: $stderr" -Level "WARN"
        }
        if ($null -ne $exitCode -and $exitCode -ne 0) {
            Write-TrayLog "LaunchSanitizer: launch-sweep exited $exitCode" -Level "WARN"
        }

        $payload = Invoke-JsonSafe -Text $stdout -Source "LaunchSweep"
        Apply-LaunchSweepPayload `
            -Payload $payload `
            -ProfileId $script:LaunchSanitizerSweepProfileId `
            -IsFirstDetection ([bool]$script:LaunchSanitizerSweepFirstDetection)
    }
    catch {
        Write-TrayLog "LaunchSanitizer: launch-sweep completion failed: $($_.Exception.Message)" -Level "WARN"
    }
    finally {
        Stop-LaunchSweepRuntime
    }
}

function Start-LaunchSweepCliProcess {
    <#
    .SYNOPSIS
    Starts the ABSO backend `launch-sweep <profile> --json` without blocking
    the WinForms UI thread. Completion is handled by Complete-LaunchSweepIfReady.
    #>
    param(
        [Parameter(Mandatory = $true)][string]$ProfileId,
        [bool]$IncludeOptIn = $false,
        [bool]$IsFirstDetection = $false
    )

    if (Test-LaunchSweepInFlight) {
        Write-TrayLog "LaunchSanitizer: sweep already running; skipping duplicate tick"
        return $false
    }

    if (-not $script:PythonExe) {
        Write-TrayLog "LaunchSanitizer: PythonExe unresolved; skipping sweep" -Level "WARN"
        return $false
    }

    $arguments = Get-AbsoBackendArgs -CommandArgs @("launch-sweep", $ProfileId, "--json")
    if ($IncludeOptIn) {
        $arguments += "--include-opt-in"
    }

    try {
        $script:LaunchSanitizerSweepOutputFile = [System.IO.Path]::GetTempFileName()
        $script:LaunchSanitizerSweepErrorFile = "$($script:LaunchSanitizerSweepOutputFile).err"
        $script:LaunchSanitizerSweepProfileId = $ProfileId
        $script:LaunchSanitizerSweepFirstDetection = $IsFirstDetection
        $script:LaunchSanitizerSweepStartedAt = [DateTime]::UtcNow

        $script:LaunchSanitizerSweepProc = Start-Process -FilePath $script:PythonExe `
            -ArgumentList $arguments `
            -NoNewWindow -PassThru -WorkingDirectory $script:ProjectRoot `
            -RedirectStandardOutput $script:LaunchSanitizerSweepOutputFile `
            -RedirectStandardError $script:LaunchSanitizerSweepErrorFile
        # PS 5.1: cache the handle now or .ExitCode reads $null after exit.
        if ($script:LaunchSanitizerSweepProc) { $null = $script:LaunchSanitizerSweepProc.Handle }

        $pollTimer = New-Object System.Windows.Forms.Timer
        $pollTimer.Interval = 400
        $pollTimer.Add_Tick({ Complete-LaunchSweepIfReady })
        $script:LaunchSanitizerSweepPollTimer = $pollTimer
        $pollTimer.Start()
        return $true
    }
    catch {
        Write-TrayLog "LaunchSanitizer: failed to start launch-sweep: $($_.Exception.Message)" -Level "WARN"
        Stop-LaunchSweepRuntime -KillProcess
        return $false
    }
}

function Invoke-LaunchSanitizerTick {
    <#
    .SYNOPSIS
    One tick of the launch sanitizer. Idempotent and cheap when the active
    profile's game is not running.
    #>
    try {
        $profileId = $script:activeProfile
        if ([string]::IsNullOrWhiteSpace($profileId)) {
            if (Test-LaunchSweepInFlight) {
                Stop-LaunchSweepRuntime -KillProcess
            }
            $script:LaunchSanitizerActiveProfileId = $null
            $script:LaunchSanitizerGameWasAlive = $false
            Clear-AbsoKeepAwake
            Stop-CpuBalancerForGame
            if ($script:LaunchSanitizerTimer -and $script:LaunchSanitizerTimer.Interval -ne $script:LaunchSanitizerIdleIntervalMs) {
                $script:LaunchSanitizerTimer.Interval = $script:LaunchSanitizerIdleIntervalMs
            }
            return
        }

        if (
            (Test-LaunchSweepInFlight) -and
            $script:LaunchSanitizerSweepProfileId -and
            $script:LaunchSanitizerSweepProfileId -ne $profileId
        ) {
            Write-TrayLog "LaunchSanitizer: active profile changed; canceling in-flight sweep for '$script:LaunchSanitizerSweepProfileId'"
            Stop-LaunchSweepRuntime -KillProcess
            Stop-CpuBalancerForGame
        }

        $profile = $script:Profiles[$profileId]
        if (-not $profile -or -not $profile.KillsetAlwaysSafe -or $profile.KillsetAlwaysSafe.Count -eq 0) {
            # Profile defines no killset (productivity etc.) - nothing to do.
            if (Test-LaunchSweepInFlight) {
                Stop-LaunchSweepRuntime -KillProcess
            }
            $script:LaunchSanitizerActiveProfileId = $profileId
            $script:LaunchSanitizerGameWasAlive = $false
            Clear-AbsoKeepAwake
            Stop-CpuBalancerForGame
            if ($script:LaunchSanitizerTimer -and $script:LaunchSanitizerTimer.Interval -ne $script:LaunchSanitizerIdleIntervalMs) {
                $script:LaunchSanitizerTimer.Interval = $script:LaunchSanitizerIdleIntervalMs
            }
            return
        }

        $gameAlive = Test-IsActiveProfileGameRunning

        if (-not $gameAlive) {
            if ($script:LaunchSanitizerGameWasAlive) {
                Write-TrayLog "LaunchSanitizer: $profileId game exited; resuming idle cadence"
                $script:LaunchSanitizerLastSweepStopped = @{}
            }
            $script:LaunchSanitizerGameWasAlive = $false
            $script:LaunchSanitizerActiveProfileId = $profileId
            Clear-AbsoKeepAwake
            Stop-CpuBalancerForGame
            if ($script:LaunchSanitizerTimer -and $script:LaunchSanitizerTimer.Interval -ne $script:LaunchSanitizerIdleIntervalMs) {
                $script:LaunchSanitizerTimer.Interval = $script:LaunchSanitizerIdleIntervalMs
            }
            return
        }

        # Keep-Awake: emulator-style profiles inhibit system/display sleep while
        # the game is alive (gamepad input does not reset the OS idle timer).
        # Idempotent: re-asserting identical flags each tick is a no-op, and an
        # alive-but-not-eligible profile (e.g. a shooter) clears any stale state.
        # The tray-config flag defaults to allowed when absent.
        $keepAwakeAllowed = $true
        if ($script:TrayConfig -and $null -ne $script:TrayConfig.keepAwakeWhileGaming) {
            $keepAwakeAllowed = [bool]$script:TrayConfig.keepAwakeWhileGaming
        }
        if ([bool]$profile.KeepAwakeWhileGaming -and $keepAwakeAllowed) {
            Set-AbsoKeepAwake
        }
        else {
            Clear-AbsoKeepAwake
        }

        # ProBalance governor: spawn the background-restraint daemon for the
        # session. Gated on the tray-config flag (default OFF — opt in per
        # machine). Self-exits when the game dies; also stopped on exit below.
        $cpuBalancerAllowed = $false
        if ($script:TrayConfig -and $null -ne $script:TrayConfig.cpuBalancer) {
            $cpuBalancerAllowed = [bool]$script:TrayConfig.cpuBalancer
        }
        if ($cpuBalancerAllowed) {
            if (-not (Test-CpuBalancerRunning)) {
                $gameProcId = Get-ActiveProfileGamePid
                if ($gameProcId) {
                    Start-CpuBalancerForGame -ProfileId $profileId -GamePid $gameProcId | Out-Null
                }
            }
        }
        elseif (Test-CpuBalancerRunning) {
            Stop-CpuBalancerForGame
        }

        $includeOptIn = $false
        if ($script:TrayConfig -and $script:TrayConfig.aggressiveProcessJanitor) {
            $includeOptIn = [bool]$script:TrayConfig.aggressiveProcessJanitor
        }

        # First detection of game-alive transitions logs a banner so the user
        # can correlate it with their session in the log.
        $isFirstDetection = -not $script:LaunchSanitizerGameWasAlive
        if ($isFirstDetection) {
            $exeList = ($profile.Exes -join ", ")
            $tier = if ($includeOptIn) { "always-safe + opt-in" } else { "always-safe" }
            Write-TrayLog "LaunchSanitizer: game detected for '$profileId' ($exeList) - sweeping $tier killset"
        }

        if (Test-LaunchSweepInFlight) {
            if ($script:LaunchSanitizerTimer -and $script:LaunchSanitizerTimer.Interval -ne $script:LaunchSanitizerActiveIntervalMs) {
                $script:LaunchSanitizerTimer.Interval = $script:LaunchSanitizerActiveIntervalMs
            }
            return
        }

        $started = Start-LaunchSweepCliProcess `
            -ProfileId $profileId `
            -IncludeOptIn $includeOptIn `
            -IsFirstDetection $isFirstDetection
        if ($started) {
            $script:LaunchSanitizerActiveProfileId = $profileId
            $script:LaunchSanitizerGameWasAlive = $true
        }
        if ($script:LaunchSanitizerTimer -and $script:LaunchSanitizerTimer.Interval -ne $script:LaunchSanitizerActiveIntervalMs) {
            $script:LaunchSanitizerTimer.Interval = $script:LaunchSanitizerActiveIntervalMs
        }
    }
    catch {
        Write-TrayLog "LaunchSanitizer tick error: $($_.Exception.Message)" -Level "WARN"
    }
}

function Start-LaunchSanitizerTimer {
    if ($script:LaunchSanitizerTimer) {
        try { $script:LaunchSanitizerTimer.Stop() } catch {}
        try { $script:LaunchSanitizerTimer.Dispose() } catch {}
    }

    $script:LaunchSanitizerTimer = New-Object System.Windows.Forms.Timer
    $script:LaunchSanitizerTimer.Interval = $script:LaunchSanitizerIdleIntervalMs
    $script:LaunchSanitizerTimer.Add_Tick({
        try { Invoke-LaunchSanitizerTick } catch {
            try { Write-TrayLog "LaunchSanitizer outer tick error: $($_.Exception.Message)" -Level "WARN" } catch {}
        }
    })
    $script:LaunchSanitizerTimer.Start()
    Write-TrayLog "LaunchSanitizer started (idle: $($script:LaunchSanitizerIdleIntervalMs)ms, active: $($script:LaunchSanitizerActiveIntervalMs)ms)"

    # Fire one immediate tick so a game that was already running when the tray
    # started gets sanitized without waiting 30 seconds.
    try { Invoke-LaunchSanitizerTick } catch {}
}

function Stop-LaunchSanitizerTimer {
    if ($script:LaunchSanitizerTimer) {
        try { $script:LaunchSanitizerTimer.Stop() } catch {}
        try { $script:LaunchSanitizerTimer.Dispose() } catch {}
        $script:LaunchSanitizerTimer = $null
    }
    Stop-LaunchSweepRuntime -KillProcess
    Clear-AbsoKeepAwake
    Stop-CpuBalancerForGame
}

function Show-AboutPanel {
    <#
    .SYNOPSIS
    Shows the branded tray About surface.

    .DESCRIPTION
    The tray's most common UI surfaces use the Penumbra visual system. The
    About action should match that system and preserve accurate status copy
    instead of falling back to a generic MessageBox.
    #>

    if ($script:AboutForm -and -not $script:AboutForm.IsDisposed) {
        try { $script:AboutForm.BringToFront() } catch {}
        try { $script:AboutForm.Activate() } catch {}
        return
    }

    $hotkeyText = Get-HotkeyRegistrationSummaryText -Config $script:TrayConfig
    $form = New-Object System.Windows.Forms.Form
    $form.Text = "About computa"
    $form.Size = New-Object System.Drawing.Size(430, 398)
    $form.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::FixedDialog
    $form.MaximizeBox = $false
    $form.MinimizeBox = $false
    $form.StartPosition = [System.Windows.Forms.FormStartPosition]::CenterScreen
    $form.BackColor = $script:Colors.Background
    $form.ForeColor = $script:Colors.Text
    $form.Font = $script:FontNormal
    $form.TopMost = $true
    $form.ShowInTaskbar = $false

    $aboutPulseTimer = $null
    $aboutTruthPulseTimer = $null

    $header = New-Object System.Windows.Forms.Panel
    $header.Location = New-Object System.Drawing.Point(10, 10)
    $header.Size = New-Object System.Drawing.Size(394, 74)
    $header.BackColor = $script:Colors.BackgroundDark
    $header.Tag = @{
        Frame = 0
        Accent = $script:Colors.AccentGold
        Blue = $script:Colors.AccentBlue
    }
    $header.Add_Paint({
        param($s, $e)
        $g = $e.Graphics
        $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
        $accent = $s.Tag["Accent"]
        $blue = $s.Tag["Blue"]
        $frame = [int]$s.Tag["Frame"]

        $bgBrush = New-Object System.Drawing.SolidBrush -ArgumentList $script:Colors.BackgroundDark
        $g.FillRectangle($bgBrush, 0, 0, $s.Width, $s.Height)
        $bgBrush.Dispose()

        $haloBrush = New-Object System.Drawing.SolidBrush -ArgumentList (
            [System.Drawing.Color]::FromArgb(42, $accent.R, $accent.G, $accent.B)
        )
        $g.FillEllipse($haloBrush, 13, 10, 46, 46)
        $haloBrush.Dispose()

        $orbitStart = ($frame * 8) % 360
        $orbitPen = New-Object System.Drawing.Pen -ArgumentList (
            [System.Drawing.Color]::FromArgb(160, $accent.R, $accent.G, $accent.B), 1.6
        )
        $orbitPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
        $orbitPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
        $g.DrawArc($orbitPen, 12, 9, 48, 48, $orbitStart, 88)
        $orbitPen.Dispose()

        $railPen = New-Object System.Drawing.Pen -ArgumentList (
            [System.Drawing.Color]::FromArgb(70, $blue.R, $blue.G, $blue.B), 1
        )
        $g.DrawLine($railPen, 72, 58, ($s.Width - 18), 58)
        $railPen.Dispose()

        $sweepX = 72 + (($frame * 7) % [Math]::Max(1, $s.Width - 150))
        $sweepPen = New-Object System.Drawing.Pen -ArgumentList (
            [System.Drawing.Color]::FromArgb(180, $accent.R, $accent.G, $accent.B), 1.2
        )
        $sweepPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
        $sweepPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
        $g.DrawLine($sweepPen, $sweepX, 58, [Math]::Min($s.Width - 18, $sweepX + 56), 58)
        $sweepPen.Dispose()

        $borderPen = New-Object System.Drawing.Pen -ArgumentList $script:Colors.Border, 1
        $g.DrawRectangle($borderPen, 0, 0, ($s.Width - 1), ($s.Height - 1))
        $borderPen.Dispose()
    })
    $form.Controls.Add($header)

    $brandBox = New-Object System.Windows.Forms.PictureBox
    $brandBox.Location = New-Object System.Drawing.Point(25, 27)
    $brandBox.Size = New-Object System.Drawing.Size(22, 22)
    $brandBox.SizeMode = [System.Windows.Forms.PictureBoxSizeMode]::Zoom
    $brandBox.BackColor = $script:Colors.BackgroundDark
    $brandBox.Image = New-ActionBitmap -Action "Brand" -Color $script:Colors.AccentGold
    $header.Controls.Add($brandBox)

    $title = New-Object System.Windows.Forms.Label
    $title.Text = "computa v$($script:AppVersion)"
    $title.Location = New-Object System.Drawing.Point(72, 16)
    $title.Size = New-Object System.Drawing.Size(210, 24)
    $title.ForeColor = $script:Colors.Text
    $title.BackColor = $script:Colors.BackgroundDark
    $title.Font = $script:FontHero
    $title.AutoEllipsis = $true
    $header.Controls.Add($title)

    $subtitle = New-Object System.Windows.Forms.Label
    $subtitle.Text = "Per-game Windows optimization"
    $subtitle.Location = New-Object System.Drawing.Point(73, 39)
    $subtitle.Size = New-Object System.Drawing.Size(242, 18)
    $subtitle.ForeColor = $script:Colors.TextDim
    $subtitle.BackColor = $script:Colors.BackgroundDark
    $subtitle.Font = $script:FontMono
    $subtitle.AutoEllipsis = $true
    $header.Controls.Add($subtitle)

    $chip = New-Object System.Windows.Forms.Label
    $chip.Text = "TRAY"
    $chip.Location = New-Object System.Drawing.Point(330, 18)
    $chip.Size = New-Object System.Drawing.Size(44, 18)
    $chip.TextAlign = [System.Drawing.ContentAlignment]::MiddleCenter
    $chip.ForeColor = $script:Colors.AccentGold
    $chip.BackColor = $script:Colors.BackgroundLight
    $chip.Font = $script:FontEyebrow
    $header.Controls.Add($chip)

    $aboutPulseTimer = New-Object System.Windows.Forms.Timer
    $aboutPulseTimer.Interval = 95
    $aboutPulseTimer.Tag = $header
    $aboutPulseTimer.Add_Tick({
        try {
            $target = $this.Tag
            if (-not $target -or $target.IsDisposed) {
                $this.Stop()
                $this.Dispose()
                return
            }
            if ($target.Tag -is [hashtable]) {
                $target.Tag["Frame"] = ([int]$target.Tag["Frame"] + 1) % 120
            }
            $target.Invalidate()
        } catch {
            try { $this.Stop(); $this.Dispose() } catch {}
        }
    })
    $aboutPulseTimer.Start()

    $infoBox = New-Object System.Windows.Forms.PictureBox
    $infoBox.Location = New-Object System.Drawing.Point(24, 104)
    $infoBox.Size = New-Object System.Drawing.Size(24, 24)
    $infoBox.SizeMode = [System.Windows.Forms.PictureBoxSizeMode]::Zoom
    $infoBox.BackColor = $script:Colors.Background
    $infoBox.Image = New-ActionBitmap -Action "Info" -Color $script:Colors.AccentBlue
    $form.Controls.Add($infoBox)

    $roleLabel = New-Object System.Windows.Forms.Label
    $roleLabel.Text = "Tray control surface"
    $roleLabel.Location = New-Object System.Drawing.Point(58, 101)
    $roleLabel.Size = New-Object System.Drawing.Size(330, 22)
    $roleLabel.ForeColor = $script:Colors.Text
    $roleLabel.BackColor = $script:Colors.Background
    $roleLabel.Font = $script:FontBold
    $form.Controls.Add($roleLabel)

    $truthLabel = New-Object System.Windows.Forms.Label
    $truthLabel.Text = "Profiles apply only from explicit tray actions. Startup profile is a reminder, not an automatic apply."
    $truthLabel.Location = New-Object System.Drawing.Point(58, 125)
    $truthLabel.Size = New-Object System.Drawing.Size(330, 38)
    $truthLabel.ForeColor = $script:Colors.TextDim
    $truthLabel.BackColor = $script:Colors.Background
    $truthLabel.Font = $script:FontNormal
    $form.Controls.Add($truthLabel)

    $truthStrip = New-Object System.Windows.Forms.Panel
    $truthStrip.Location = New-Object System.Drawing.Point(24, 170)
    $truthStrip.Size = New-Object System.Drawing.Size(364, 46)
    $truthStrip.BackColor = $script:Colors.BackgroundLight
    $truthStrip.Tag = @{
        Accent = $script:Colors.AccentBlue
        Gold = $script:Colors.AccentGold
        Frame = 0
    }
    $truthStrip.Add_Paint({
        param($s, $e)
        $g = $e.Graphics
        $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
        $state = if ($s.Tag -is [hashtable]) { $s.Tag } else { @{} }
        $accent = if ($state.ContainsKey("Accent") -and $state["Accent"] -is [System.Drawing.Color]) {
            $state["Accent"]
        } else {
            $script:Colors.AccentBlue
        }
        $gold = if ($state.ContainsKey("Gold") -and $state["Gold"] -is [System.Drawing.Color]) {
            $state["Gold"]
        } else {
            $script:Colors.AccentGold
        }
        $frame = if ($state.ContainsKey("Frame")) { [int]$state["Frame"] } else { 0 }
        $borderPen = New-Object System.Drawing.Pen -ArgumentList (
            [System.Drawing.Color]::FromArgb(70, $accent.R, $accent.G, $accent.B), 1
        )
        $g.DrawRectangle($borderPen, 0, 0, ($s.Width - 1), ($s.Height - 1))
        $borderPen.Dispose()
        $sweepX = 10 + (($frame * 5) % [Math]::Max(1, $s.Width - 42))
        $sweepPen = New-Object System.Drawing.Pen -ArgumentList (
            [System.Drawing.Color]::FromArgb(135, $gold.R, $gold.G, $gold.B), 1.1
        )
        $sweepPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
        $sweepPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
        $g.DrawLine($sweepPen, $sweepX, 4, [Math]::Min(($s.Width - 10), ($sweepX + 32)), 4)
        $sweepPen.Dispose()
    })
    $form.Controls.Add($truthStrip)
    $aboutTruthPulseTimer = New-Object System.Windows.Forms.Timer
    $aboutTruthPulseTimer.Interval = 115
    $aboutTruthPulseTimer.Tag = $truthStrip
    $aboutTruthPulseTimer.Add_Tick({
        try {
            $target = $this.Tag
            if (-not $target -or $target.IsDisposed) {
                $this.Stop()
                $this.Dispose()
                return
            }
            if ($target.Tag -is [hashtable]) {
                $target.Tag["Frame"] = ([int]$target.Tag["Frame"] + 1) % 120
            }
            $target.Invalidate()
        } catch {
            try { $this.Stop(); $this.Dispose() } catch {}
        }
    })
    $aboutTruthPulseTimer.Start()

    $applyTruthIcon = New-Object System.Windows.Forms.PictureBox
    $applyTruthIcon.Location = New-Object System.Drawing.Point(10, 13)
    $applyTruthIcon.Size = New-Object System.Drawing.Size(18, 18)
    $applyTruthIcon.SizeMode = [System.Windows.Forms.PictureBoxSizeMode]::Zoom
    $applyTruthIcon.BackColor = $truthStrip.BackColor
    $applyTruthIcon.Image = New-ActionBitmap -Action "Apply" -Color $script:Colors.AccentGreen
    $truthStrip.Controls.Add($applyTruthIcon)

    $applyTruthLabel = New-Object System.Windows.Forms.Label
    $applyTruthLabel.Text = "Explicit apply"
    $applyTruthLabel.Location = New-Object System.Drawing.Point(32, 12)
    $applyTruthLabel.Size = New-Object System.Drawing.Size(84, 20)
    $applyTruthLabel.ForeColor = $script:Colors.Text
    $applyTruthLabel.BackColor = $truthStrip.BackColor
    $applyTruthLabel.Font = $script:FontEyebrow
    $applyTruthLabel.AutoEllipsis = $true
    $truthStrip.Controls.Add($applyTruthLabel)

    $startupTruthIcon = New-Object System.Windows.Forms.PictureBox
    $startupTruthIcon.Location = New-Object System.Drawing.Point(130, 13)
    $startupTruthIcon.Size = New-Object System.Drawing.Size(18, 18)
    $startupTruthIcon.SizeMode = [System.Windows.Forms.PictureBoxSizeMode]::Zoom
    $startupTruthIcon.BackColor = $truthStrip.BackColor
    $startupTruthIcon.Image = New-ActionBitmap -Action "Startup" -Color $script:Colors.AccentGold
    $truthStrip.Controls.Add($startupTruthIcon)

    $startupTruthLabel = New-Object System.Windows.Forms.Label
    $startupTruthLabel.Text = "Reminder only"
    $startupTruthLabel.Location = New-Object System.Drawing.Point(152, 12)
    $startupTruthLabel.Size = New-Object System.Drawing.Size(88, 20)
    $startupTruthLabel.ForeColor = $script:Colors.Text
    $startupTruthLabel.BackColor = $truthStrip.BackColor
    $startupTruthLabel.Font = $script:FontEyebrow
    $startupTruthLabel.AutoEllipsis = $true
    $truthStrip.Controls.Add($startupTruthLabel)

    $hotkeyTruthIcon = New-Object System.Windows.Forms.PictureBox
    $hotkeyTruthIcon.Location = New-Object System.Drawing.Point(254, 13)
    $hotkeyTruthIcon.Size = New-Object System.Drawing.Size(18, 18)
    $hotkeyTruthIcon.SizeMode = [System.Windows.Forms.PictureBoxSizeMode]::Zoom
    $hotkeyTruthIcon.BackColor = $truthStrip.BackColor
    $hotkeyTruthIcon.Image = New-ActionBitmap -Action "Hotkey" -Color $script:Colors.AccentBlue
    $truthStrip.Controls.Add($hotkeyTruthIcon)

    $hotkeyTruthLabel = New-Object System.Windows.Forms.Label
    $hotkeyTruthLabel.Text = "Session state"
    $hotkeyTruthLabel.Location = New-Object System.Drawing.Point(276, 12)
    $hotkeyTruthLabel.Size = New-Object System.Drawing.Size(82, 20)
    $hotkeyTruthLabel.ForeColor = $script:Colors.Text
    $hotkeyTruthLabel.BackColor = $truthStrip.BackColor
    $hotkeyTruthLabel.Font = $script:FontEyebrow
    $hotkeyTruthLabel.AutoEllipsis = $true
    $truthStrip.Controls.Add($hotkeyTruthLabel)

    $hotkeyLabel = New-Object System.Windows.Forms.Label
    $hotkeyLabel.Text = $hotkeyText
    $hotkeyLabel.Location = New-Object System.Drawing.Point(24, 232)
    $hotkeyLabel.Size = New-Object System.Drawing.Size(364, 76)
    $hotkeyLabel.ForeColor = $script:Colors.TextDim
    $hotkeyLabel.BackColor = $script:Colors.BackgroundLight
    $hotkeyLabel.Font = $script:FontMono
    $form.Controls.Add($hotkeyLabel)

    $closeBtn = New-Object System.Windows.Forms.Button
    $closeBtn.Text = "Close"
    $closeBtn.Location = New-Object System.Drawing.Point(302, 312)
    $closeBtn.Size = New-Object System.Drawing.Size(86, 32)
    $closeBtn.BackColor = $script:Colors.BackgroundLight
    $closeBtn.ForeColor = $script:Colors.Text
    $closeBtn.FlatStyle = [System.Windows.Forms.FlatStyle]::Flat
    $closeBtn.FlatAppearance.BorderSize = 0
    $closeBtn.Font = $script:FontNormal
    $closeBtn.Cursor = [System.Windows.Forms.Cursors]::Hand
    $closeBtn.Image = New-ActionBitmap -Action "Close" -Color $script:Colors.TextDim
    $closeBtn.ImageAlign = [System.Drawing.ContentAlignment]::MiddleLeft
    $closeBtn.TextImageRelation = [System.Windows.Forms.TextImageRelation]::ImageBeforeText
    $closeBtn.Padding = New-Object System.Windows.Forms.Padding(8, 0, 6, 0)
    $closeBtn.Add_Click({ $form.Close() })
    $form.Controls.Add($closeBtn)

    $script:AboutForm = $form
    $form.Add_FormClosed({
        if ($aboutPulseTimer) {
            try { $aboutPulseTimer.Stop() } catch {}
            try { $aboutPulseTimer.Dispose() } catch {}
        }
        if ($aboutTruthPulseTimer) {
            try { $aboutTruthPulseTimer.Stop() } catch {}
            try { $aboutTruthPulseTimer.Dispose() } catch {}
        }
        foreach ($control in @($brandBox, $infoBox, $closeBtn, $applyTruthIcon, $startupTruthIcon, $hotkeyTruthIcon)) {
            if ($control -and $control.Image) {
                $image = $control.Image
                $control.Image = $null
                try { $image.Dispose() } catch {}
            }
        }
        $form.Dispose()
        $script:AboutForm = $null
    }.GetNewClosure())

    $form.Show()
    try {
        Apply-DwmWindowEffects -Form $form -CornerStyle 2 -BorderColorRGB @(0, 245, 212)
    } catch {}
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
        # Race-prevention buffer is only needed at BOOT (explorer just started
        # initializing the notification area). For manual restarts via the tray
        # menu, explorer has been up for ages and the buffer is pure waste.
        $needsBootBuffer = $true
        try {
            $explorerProc = Get-Process -Name explorer -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($explorerProc) {
                $explorerUptime = (Get-Date) - $explorerProc.StartTime
                if ($explorerUptime.TotalSeconds -gt 30) {
                    $needsBootBuffer = $false
                }
            }
        } catch { }
        if ($needsBootBuffer) {
            # Boot scenario: notification area still spinning up.
            Start-Sleep -Milliseconds 1500
        }
    }

    # Load config
    $script:TrayConfig = Read-TrayConfig
    $script:EnableBalloonNotifications = [bool]$script:TrayConfig.notificationsEnabled
    $normalizeResult = Normalize-TrayConfigProfileIds -Config $script:TrayConfig
    $script:TrayConfig = $normalizeResult.Config
    if ($normalizeResult.Changed) {
        Write-TrayLog "Normalized retired profile ids in tray-config.json via alias map" -Level "INFO"
        Save-TrayConfig $script:TrayConfig
    }
    $script:LastAction = $null
    $script:LastActionTime = $null
    $script:AuditIssueCount = 0

    $script:notifyIcon = New-Object System.Windows.Forms.NotifyIcon
    Set-IconState -State "Idle"
    Set-TrayOperationTooltipText -Text "computa - Ready"
    $script:notifyIcon.Visible = $true
    Start-StartupIconSelfHeal

    # Restore startup state using the freshest candidate across state files and tray metadata.
    $script:activeProfile = $null
    $startupProfile = Resolve-StartupActiveProfile -Config $script:TrayConfig -ProfileMap $script:Profiles
    $script:TrayConfig = Set-StartupResolutionRecord -Config $script:TrayConfig -Record $startupProfile
    if ($startupProfile -and $startupProfile.sync_state_path) {
        try { [void](Repair-StartupActiveProfileState -Record $startupProfile) } catch {}
    }
    if ($startupProfile -and $startupProfile.status -eq "active" -and $startupProfile.id) {
        $script:activeProfile = "$($startupProfile.id)"
        $startupProfileName = if ($startupProfile.name) {
            Format-TrayDisplayCopy -Text "$($startupProfile.name)"
        }
        else {
            Get-TrayProfileDisplayName -ProfileId $script:activeProfile
        }
        $stateSource = if ($startupProfile.source) { "$($startupProfile.source)" } else { "startup_restore" }
        $restoreSource = Get-StartupRestoreStateSource -Source $stateSource
        $stateTimestamp = if ($startupProfile.timestamp) { "$($startupProfile.timestamp)" } else { (Get-Date).ToString("o") }
        $script:TrayConfig = Set-LastProfileState `
            -Config $script:TrayConfig `
            -Status "active" `
            -ProfileId $script:activeProfile `
            -ProfileName $startupProfileName `
            -Source $restoreSource `
            -Timestamp $stateTimestamp
        Write-TrayLog "Startup restore selected active profile '$($startupProfile.id)' from '$($startupProfile.source)' (decision=$($startupProfile.decision), timestamp=$($startupProfile.timestamp))"
    }
    elseif ($startupProfile -and $startupProfile.status -eq "restored") {
        Write-TrayLog "Startup restore selected no active profile from '$($startupProfile.source)' (decision=$($startupProfile.decision), timestamp=$($startupProfile.timestamp))"
    }
    else {
        Write-TrayLog "No previously active profile restored at startup"
    }
    $script:profileMenuItems = @()

    # Sweep any orphan power-switcher state file left over from older builds
    # whose Apply-Profile wrote a pre-game plan GUID. The writer was removed
    # so there is no recovery to do; the stale file is just clutter.
    try {
        $powerStateFile = Join-Path $script:ProjectRoot ".power_switcher_state.json"
        if (Test-Path $powerStateFile) {
            Remove-Item $powerStateFile -Force -ErrorAction SilentlyContinue
            Write-TrayLog "Removed orphan .power_switcher_state.json from older tray build"
        }
    } catch {
        Write-TrayLog "Power state cleanup failed: $($_.Exception.Message)" -Level "WARN"
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
        $hotkeyRegistration = Register-GlobalHotkeys -WindowHandle $script:HotkeyWindow.Handle -Config $script:TrayConfig -Actions @{
            openMenu = {
                $mi = $script:notifyIcon.GetType().GetMethod(
                    "ShowContextMenu",
                    [System.Reflection.BindingFlags]::Instance -bor [System.Reflection.BindingFlags]::NonPublic
                )
                $mi.Invoke($script:notifyIcon, $null)
            }
            restore = {
                if ($script:activeProfile) {
                    Restore-Settings
                }
                else {
                    Show-Notification -Title "computa" -Message "No active profile to restore. Apply a profile first." -Type "Info" -ActionName "Restore" -ActionColor $script:Colors.AccentAmber
                    Set-TrayLastAction -Message "Restore hotkey ignored: no active profile"
                    Update-MenuState
                }
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

        if ($hotkeyRegistration.Active -gt 0 -and $hotkeyRegistration.Failed -le 0) {
            Write-TrayLog "Global hotkeys active: $($hotkeyRegistration.Active)/$($hotkeyRegistration.Total)"
        }
        elseif ($hotkeyRegistration.Active -gt 0) {
            Write-TrayLog "Global hotkeys partially active: $($hotkeyRegistration.Active)/$($hotkeyRegistration.Total)" -Level "WARN"
        }
        else {
            Write-TrayLog "No global hotkeys active; configured keys may be unavailable" -Level "WARN"
        }
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
    Set-TrayDropDownWidthBudget -DropDown $menu
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
            Set-TrayDropDownWidthBudget -DropDown $menu
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
            Set-TrayDropDownWidthBudget -DropDown $item.DropDown
            $item.DropDown.Add_Opened({
                param($ds, $de)
                try {
                    Set-TrayDropDownWidthBudget -DropDown $ds
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
    $header.Text = "computa   v$($script:AppVersion)"
    $header.Enabled = $false
    $header.BackColor = $script:Colors.BackgroundDark
    $header.ForeColor = $script:Colors.AccentGold
    $header.Font = [DarkThemeRenderer]::ResolveHeroFont(12.6, [System.Drawing.FontStyle]::Bold)
    $header.Image = New-ActionBitmap -Action "Brand" -Color $script:Colors.AccentGold
    $menu.Items.Add($header) | Out-Null

    # ─── STATUS DASHBOARD ───

    $sysInfo = Get-SystemInfo

    $script:statusItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $script:statusItem.Tag = "__hero_banner__"
    $script:statusItem.AutoSize = $false
    $script:statusItem.Size = New-Object System.Drawing.Size(480, 48)
    $script:statusItem.Padding = New-Object System.Windows.Forms.Padding(0)
    $script:statusItem.Margin = New-Object System.Windows.Forms.Padding(0)
    $script:statusItem.Enabled = $false
    $script:statusItem.BackColor = $script:Colors.BackgroundDark
    $script:statusItem.Font = $script:FontMenuRowBold
    Set-TrayActiveStatusItemFromState
    $menu.Items.Add($script:statusItem) | Out-Null

    # System info line (GPU + display topology summary)
    $sysInfoText = "$($sysInfo.GPU)  |  $($sysInfo.DisplaySummary)"
    $sysInfoItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $sysInfoItem.Text = $sysInfoText
    $sysInfoItem.AccessibleName = "__status_bar__"
    $sysInfoItem.AccessibleDescription = Get-TraySystemInfoChipText -GpuName $sysInfo.GPU -DisplaySummary $sysInfo.DisplaySummary
    $sysInfoItem.Enabled = $false
    $sysInfoItem.BackColor = $script:Colors.BackgroundDark
    $sysInfoItem.ForeColor = $script:Colors.TextDisabled
    $sysInfoItem.Font = $script:FontMono
    $sysInfoItem.Image = New-TrayDisplayTopologyBitmap -DisplaySummary $sysInfo.DisplaySummary -Color $script:Colors.TextDisabled
    $menu.Items.Add($sysInfoItem) | Out-Null

    # Audit status item (hidden until audit is run)
    $script:auditStatusItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $script:auditStatusItem.Text = ""
    $script:auditStatusItem.AccessibleName = "__status_bar__"
    $script:auditStatusItem.AccessibleDescription = "AUDIT"
    $script:auditStatusItem.Enabled = $false
    $script:auditStatusItem.BackColor = $script:Colors.BackgroundDark
    $script:auditStatusItem.ForeColor = $script:Colors.AccentGreen
    $script:auditStatusItem.Font = New-Object System.Drawing.Font("Segoe UI", 8.6)
    $script:auditStatusItem.Image = New-AuditStatusBitmap -Color $script:Colors.AccentGreen
    $script:auditStatusItem.Visible = $false
    $menu.Items.Add($script:auditStatusItem) | Out-Null

    # ─── SEARCH ───

    $menu.Items.Add((New-Object System.Windows.Forms.ToolStripSeparator)) | Out-Null

    $searchBox = New-Object System.Windows.Forms.ToolStripTextBox
    $searchBox.Size = New-Object System.Drawing.Size(300, 26)
    $searchBox.BackColor = $script:Colors.BackgroundLight
    $searchBox.ForeColor = $script:Colors.Text
    $searchBox.Font = $script:FontMenuRow
    $searchBox.ToolTipText = "Search profiles... (type to filter)"
    # Placeholder text
    $searchBox.Text = "Search profiles..."
    $searchBox.ForeColor = $script:Colors.TextDim
    $script:searchIsPlaceholder = $true

    $searchBox.Add_GotFocus({
        if ($script:searchIsPlaceholder) {
            $script:searchIsPlaceholder = $false
            $this.Text = ""
            $this.ForeColor = $script:Colors.Text
        }
    })
    $searchBox.Add_LostFocus({
        if ($this.Text -eq "") {
            $script:searchIsPlaceholder = $true
            $this.Text = "Search profiles..."
            $this.ForeColor = $script:Colors.TextDim
        }
    })

    $script:searchStatusItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $script:searchStatusItem.Text = ""
    $script:searchStatusItem.AccessibleName = "__status_bar__"
    $script:searchStatusItem.AccessibleDescription = "SEARCH"
    $script:searchStatusItem.Enabled = $false
    $script:searchStatusItem.Visible = $false
    $script:searchStatusItem.BackColor = $script:Colors.BackgroundDark
    $script:searchStatusItem.ForeColor = $script:Colors.TextDim
    $script:searchStatusItem.Font = $script:FontEyebrow
    $script:searchStatusItem.Image = New-ActionBitmap -Action "Search" -Color $script:Colors.TextDim

    $searchBox.Add_TextChanged({
        if (-not $script:searchIsPlaceholder) {
            $query = $this.Text
            $matchedIds = Find-Profiles -Query $query
            Set-TraySearchStatus -Query $query -MatchedIds $matchedIds
            foreach ($item in $script:profileMenuItems) {
                $item.Visible = ($matchedIds -contains $item.Tag)
            }
            # Show/hide game group submenus based on whether any children match
            foreach ($submenuItem in $script:gameGroupSubmenus) {
                $hasVisible = $false
                foreach ($child in $submenuItem.DropDownItems) {
                    if (
                        $child -is [System.Windows.Forms.ToolStripMenuItem] -and
                        $child.Tag -ne "__game_flyout_header__" -and
                        $child.Visible
                    ) {
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
    $menu.Items.Add($script:searchStatusItem) | Out-Null

    # --- Derive game groups from catalog metadata ---
    # The Python manifest now carries explicit group/variant labels so games
    # appear once with their SDR/HDR/sync options underneath. The suffix list
    # remains only as a fallback for stale caches or user YAML profiles.
    $variantSuffixes = @(
        "-online-gsync-hdr-capture", "-online-gsync-hdr",
        "-gsync-hdr-capture", "-gsync-capture",
        "-online-gsync", "-offline-gsync-hdr",
        "-offline-hdr", "-online-hdr", "-console-parity-hdr",
        "-universal-hdr", "-gsync-hdr", "-tournament-sim-144hz",
        "-console-parity", "-300hz-max", "-streaming-hdr", "-streaming",
        "-offline", "-online", "-vrr-lab", "-gsync", "-hdr", "-sdr",
        "-universal", "-capture"
    )

    function Get-GameGroup {
        param([string]$ProfileId)
        $profile = $null
        if ($script:Profiles -and $script:Profiles.Contains($ProfileId)) {
            $profile = $script:Profiles[$ProfileId]
        }
        if ($profile -and -not [string]::IsNullOrWhiteSpace("$($profile.GameGroup)")) {
            return "$($profile.GameGroup)"
        }
        foreach ($suffix in $variantSuffixes) {
            if ($ProfileId.EndsWith($suffix)) {
                return $ProfileId.Substring(0, $ProfileId.Length - $suffix.Length)
            }
        }
        return $ProfileId
    }

    function Get-GameGroupName {
        param([string]$ProfileId)
        $profile = $null
        if ($script:Profiles -and $script:Profiles.Contains($ProfileId)) {
            $profile = $script:Profiles[$ProfileId]
        }
        if ($profile -and -not [string]::IsNullOrWhiteSpace("$($profile.GroupName)")) {
            return (Format-TrayDisplayCopy -Text "$($profile.GroupName)")
        }
        if ($profile -and $profile.Name) {
            return ((Format-TrayDisplayCopy -Text "$($profile.Name)") -replace '(:|\s+-\s+).*$', '')
        }
        return $ProfileId
    }

    function Get-ProfileVariantLabel {
        param([string]$ProfileId)
        $profile = $null
        if ($script:Profiles -and $script:Profiles.Contains($ProfileId)) {
            $profile = $script:Profiles[$ProfileId]
        }
        if ($profile -and -not [string]::IsNullOrWhiteSpace("$($profile.Variant)")) {
            return (Format-TrayDisplayCopy -Text "$($profile.Variant)")
        }
        if ($profile -and $profile.Name) { return (Format-TrayDisplayCopy -Text "$($profile.Name)") }
        return $ProfileId
    }

    function Get-ProfileMenuDisplayText {
        param([string]$ProfileId, [bool]$InSubmenu = $false)
        $profile = $null
        if ($script:Profiles -and $script:Profiles.Contains($ProfileId)) {
            $profile = $script:Profiles[$ProfileId]
        }
        if ($InSubmenu) { return (Get-ProfileVariantLabel -ProfileId $ProfileId) }
        if ($profile -and $profile.Name) { return (Format-TrayDisplayCopy -Text "$($profile.Name)") }
        return $ProfileId
    }

    function New-TrayProfileMenuImage {
        param(
            [string]$ProfileId,
            [bool]$IsActive = $false,
            [bool]$InSubmenu = $false,
            [bool]$ShowSyncBadge = $false,
            [bool]$FavoriteBadge = $false
        )

        $profile = $null
        if ($script:Profiles -and $script:Profiles.Contains($ProfileId)) {
            $profile = $script:Profiles[$ProfileId]
        }

        $category = if ($profile -and -not [string]::IsNullOrWhiteSpace("$($profile.Cat)")) { "$($profile.Cat)" } else { "Other" }
        $catColor = Get-TrayProfileAccentColor -ProfileId $ProfileId -Profile $profile -Fallback $script:Colors.Text
        $gameGroup = Get-TrayProfileGameGroup -ProfileId $ProfileId -Profile $profile
        $variant = if ($profile -and $profile.Variant) { "$($profile.Variant)" } else { "" }
        $modeBadge = if ("$ProfileId" -match '(?i)capture' -or $variant -match '(?i)capture') {
            "capture"
        }
        elseif ($variant -match '(?i)\bHDR\b' -or "$ProfileId" -match '(?i)-hdr($|-)' ) {
            "hdr"
        }
        else {
            ""
        }

        if ($IsActive) {
            $pendingApplyBadge = -not [string]::IsNullOrWhiteSpace((Get-ActiveProfilePendingApplyText))
            $windowsRestartBadge = (
                -not $pendingApplyBadge -and
                -not [string]::IsNullOrWhiteSpace((Get-ActiveProfileRebootPendingText))
            )
            $verificationBadge = (
                -not $pendingApplyBadge -and
                -not $windowsRestartBadge -and
                -not [string]::IsNullOrWhiteSpace((Get-ActiveProfileVerificationInProgressText))
            )
            return New-ActiveGameBitmap `
                -GameGroup $gameGroup `
                -Color $catColor `
                -Category $category `
                -ModeBadge $modeBadge `
                -FavoriteBadge $FavoriteBadge `
                -PendingApplyBadge $pendingApplyBadge `
                -WindowsRestartBadge $windowsRestartBadge `
                -VerificationBadge $verificationBadge
        }

        if ($FavoriteBadge -and (Get-Command New-FavoriteGameBitmap -ErrorAction SilentlyContinue)) {
            $syncMode = if ($profile -and $profile.SyncMode) { $profile.SyncMode } else { "agnostic" }
            return New-FavoriteGameBitmap `
                -GameGroup $gameGroup `
                -Color $catColor `
                -Category $category `
                -SyncMode $syncMode `
                -ModeBadge $modeBadge
        }

        if ($InSubmenu -or $ShowSyncBadge) {
            $syncMode = if ($profile -and $profile.SyncMode) { $profile.SyncMode } else { "agnostic" }
            return New-GameSyncBadgeBitmap `
                -GameGroup $gameGroup `
                -Color $catColor `
                -Category $category `
                -SyncMode $syncMode `
                -ModeBadge $modeBadge
        }

        return New-GameBitmap -GameGroup $gameGroup -Color $catColor -Category $category
    }

    function New-TrayGameGroupMedallionBitmap {
        param(
            [string]$GameGroup,
            [System.Drawing.Color]$Color,
            [string]$Category = "Other"
        )

        $mark = New-GameBitmap -GameGroup $GameGroup -Color $Color -Category $Category
        if (-not $mark) { return $null }

        $bmp = New-Object System.Drawing.Bitmap(16, 16)
        $g = [System.Drawing.Graphics]::FromImage($bmp)
        $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
        $g.Clear([System.Drawing.Color]::Transparent)

        $glowBrush = New-Object System.Drawing.SolidBrush -ArgumentList (
            [System.Drawing.Color]::FromArgb(42, $Color.R, $Color.G, $Color.B)
        )
        $backBrush = New-Object System.Drawing.SolidBrush -ArgumentList $script:Colors.BackgroundDark
        $ringPen = New-Object System.Drawing.Pen -ArgumentList (
            [System.Drawing.Color]::FromArgb(150, $Color.R, $Color.G, $Color.B), 1
        )
        $arcPen = New-Object System.Drawing.Pen -ArgumentList (
            [System.Drawing.Color]::FromArgb(90, $Color.R, $Color.G, $Color.B), 1
        )
        $arcPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
        $arcPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round

        try {
            $g.FillEllipse($glowBrush, 0, 0, 16, 16)
            $g.FillEllipse($backBrush, 2, 2, 12, 12)
            $g.DrawEllipse($ringPen, 2, 2, 12, 12)
            $g.DrawArc($arcPen, 1, 1, 14, 14, 215, 50)
            $g.DrawImage($mark, (New-Object System.Drawing.Rectangle(3, 3, 10, 10)))
        }
        finally {
            $arcPen.Dispose()
            $ringPen.Dispose()
            $backBrush.Dispose()
            $glowBrush.Dispose()
            $g.Dispose()
            $mark.Dispose()
        }

        return $bmp
    }

    function Get-TrayProfileMenuAccent {
        param([string]$ProfileId, [object]$Profile)

        $baseColor = Get-CategoryColor -Category $Profile.Cat -Fallback $script:Colors.Text
        $gameGroup = Get-GameGroup -ProfileId $ProfileId
        if (Get-Command Get-GameAccentColor -ErrorAction SilentlyContinue) {
            return Get-GameAccentColor -GameGroup $gameGroup -FallbackColor $baseColor
        }
        return $baseColor
    }

    function Get-ProfileMenuChipText {
        param([string]$ProfileId, [object]$Profile)

        if (-not $Profile) { return "" }

        $variant = if ($Profile.Variant) { "$($Profile.Variant)" } else { "" }
        $syncMode = if ($Profile.SyncMode) { "$($Profile.SyncMode)".ToLowerInvariant() } else { "" }
        if ("$ProfileId" -match '(?i)capture' -or $variant -match '(?i)capture') { return "CAPTURE" }
        if ($syncMode -eq "on") { return "G-SYNC" }
        if ($syncMode -eq "off") { return "NO-SYNC" }
        if ($variant -match '(?i)\bHDR\b' -or "$ProfileId" -match '(?i)-hdr($|-)' ) { return "HDR" }
        if ($variant -match '(?i)\bSDR\b' -or "$ProfileId" -match '(?i)-sdr($|-)' ) { return "SDR" }
        if ($variant -match '(?i)\bonline\b') { return "ONLINE" }
        if ($variant -match '(?i)\boffline\b') { return "OFFLINE" }
        return ""
    }

    function Get-ProfileMenuActiveStateChipText {
        param([string]$ProfileId)

        if ([string]::IsNullOrWhiteSpace($ProfileId)) { return "" }
        if ([string]::IsNullOrWhiteSpace([string]$script:activeProfile)) { return "" }
        if ("$ProfileId" -ne "$script:activeProfile") { return "" }
        if (Get-ActiveProfilePendingApplyText) { return "FIX" }
        if (Get-ActiveProfileRebootPendingText) { return "RESTART" }
        if (Get-ActiveProfileVerificationInProgressText) { return "CHECK" }
        return ""
    }

    function Get-ProfileMenuActiveStateTooltipText {
        param([string]$ProfileId)

        if ([string]::IsNullOrWhiteSpace($ProfileId)) { return "" }
        if ([string]::IsNullOrWhiteSpace([string]$script:activeProfile)) { return "" }
        if ("$ProfileId" -ne "$script:activeProfile") { return "" }

        $pendingText = Get-ActiveProfilePendingApplyText
        if (-not [string]::IsNullOrWhiteSpace($pendingText)) {
            if ($script:ActiveProfileVerificationStatus -eq "mismatch") {
                return "Active state: profile mismatch for $pendingText"
            }
            return "Active state: pending profile fix for $pendingText"
        }

        $rebootText = Get-ActiveProfileRebootPendingText
        if (-not [string]::IsNullOrWhiteSpace($rebootText)) {
            return "Active state: Windows restart required for $rebootText"
        }

        if (Get-ActiveProfileVerificationInProgressText) {
            return "Active state: checking profile state"
        }

        return ""
    }

    function Set-TrayProfileMenuItemTooltipState {
        param(
            [System.Windows.Forms.ToolStripMenuItem]$Item,
            [string]$StateText = ""
        )

        if (-not $Item) { return }

        # Native ToolStrip tooltips float over the owner-drawn profile list.
        # State is rendered by row chips and the active-profile status rows.
        $Item.ToolTipText = ""
    }

    function Get-TrayProfileChipPaddingRight {
        param([int]$ChipCount)

        if ($ChipCount -le 0) { return 0 }
        return [Math]::Min(260, 82 + (($ChipCount - 1) * 72))
    }

    function Set-TrayProfileMenuItemMetadata {
        param(
            [System.Windows.Forms.ToolStripMenuItem]$Item,
            [string]$ProfileId,
            [object]$Profile,
            [string]$ExtraChipText = ""
        )

        if (-not $Item) { return }
        $chipText = Get-ProfileMenuChipText -ProfileId $ProfileId -Profile $Profile
        $stateChipText = Get-ProfileMenuActiveStateChipText -ProfileId $ProfileId
        $stateTooltipText = Get-ProfileMenuActiveStateTooltipText -ProfileId $ProfileId
        if (
            [string]::IsNullOrWhiteSpace($ExtraChipText) -and
            $Item.AccessibleDescription -and
            "$($Item.AccessibleDescription)" -match '(^|\|)RECENT(\||$)'
        ) {
            $ExtraChipText = "RECENT"
        }
        $chips = @()
        if (-not [string]::IsNullOrWhiteSpace($chipText)) { $chips += $chipText }
        if (-not [string]::IsNullOrWhiteSpace($ExtraChipText)) { $chips += $ExtraChipText.Trim().ToUpperInvariant() }
        if (-not [string]::IsNullOrWhiteSpace($stateChipText)) { $chips += $stateChipText }
        if ($chips.Count -le 0) {
            $Item.AccessibleName = "__profile_menu_item__"
            $Item.AccessibleDescription = ""
            $Item.Padding = New-Object System.Windows.Forms.Padding(0)
            Set-TrayProfileMenuItemTooltipState -Item $Item -StateText $stateTooltipText
            return
        }

        $Item.AccessibleName = "__profile_menu_item__"
        $Item.AccessibleDescription = ($chips -join "|")
        $paddingRight = Get-TrayProfileChipPaddingRight -ChipCount $chips.Count
        $Item.Padding = New-Object System.Windows.Forms.Padding(0, 0, $paddingRight, 0)
        Set-TrayProfileMenuItemTooltipState -Item $Item -StateText $stateTooltipText
    }

    function Get-GameFlyoutHeaderSummaryChips {
        param([string[]]$ProfileIds)

        $syncOn = 0
        $syncOff = 0
        $hdr = 0
        $capture = 0
        foreach ($profileId in @($ProfileIds)) {
            if (-not $profileId -or -not $script:Profiles.Contains($profileId)) { continue }
            $profile = $script:Profiles[$profileId]
            $variant = if ($profile.Variant) { "$($profile.Variant)" } else { "" }
            $syncMode = if ($profile.SyncMode) { "$($profile.SyncMode)".ToLowerInvariant() } else { "" }
            if ($syncMode -eq "on") { $syncOn += 1 }
            elseif ($syncMode -eq "off") { $syncOff += 1 }
            if ("$profileId" -match '(?i)-hdr($|-)' -or $variant -match '(?i)\bHDR\b') { $hdr += 1 }
            if ("$profileId" -match '(?i)capture' -or $variant -match '(?i)capture') { $capture += 1 }
        }

        $chips = @()
        if ($syncOn -gt 0) { $chips += "${syncOn} G-SYNC" }
        if ($syncOff -gt 0) { $chips += "${syncOff} NO-SYNC" }
        if ($hdr -gt 0) { $chips += "${hdr} HDR" }
        if ($capture -gt 0) { $chips += "${capture} CAP" }
        return ($chips -join "|")
    }

    function Get-CategoryHeaderSummaryChips {
        param(
            [int]$GameCount,
            [int]$ProfileCount
        )

        $gameLabel = if ($GameCount -eq 1) { "game" } else { "games" }
        $profileLabel = if ($ProfileCount -eq 1) { "profile" } else { "profiles" }
        return "$GameCount $gameLabel, $ProfileCount $profileLabel"
    }

    function Get-TraySectionHeaderSummaryChips {
        param(
            [int]$ItemCount,
            [string]$ItemSingular,
            [string]$ItemPlural,
            [int]$GameCount = 0
        )

        $safeItemCount = [Math]::Max(0, $ItemCount)
        $itemLabel = if ($safeItemCount -eq 1) { $ItemSingular } else { $ItemPlural }
        if ($GameCount -gt 0) {
            $safeGameCount = [Math]::Max(0, $GameCount)
            $gameLabel = if ($safeGameCount -eq 1) { "game" } else { "games" }
            return "$safeItemCount $itemLabel, $safeGameCount $gameLabel"
        }
        return "$safeItemCount $itemLabel"
    }

    function Set-TraySectionHeaderVisualState {
        param(
            [System.Windows.Forms.ToolStripMenuItem]$Item,
            [string]$ChipText
        )

        if (-not $Item) { return }
        $Item.AccessibleName = "__section_header__"
        $Item.AccessibleDescription = ""
        if (-not [string]::IsNullOrWhiteSpace($ChipText)) {
            $Item.ToolTipText = $ChipText.Trim()
        }
        # Space-above > space-below so the band binds to the rows it labels
        # (the eyebrow font is small; padding keeps the band proportionate).
        $Item.Padding = New-Object System.Windows.Forms.Padding(0, 7, 0, 3)
    }

    # ─── FAVORITES ───

    $favProfiles = @()
    foreach ($favId in $script:TrayConfig.favorites) {
        if ($script:Profiles.Contains($favId)) {
            $favProfiles += $favId
        }
    }

    if ($favProfiles.Count -gt 0) {
        $favoriteHeaderGameGroups = [System.Collections.Generic.List[string]]::new()
        $favoriteHeaderGroupKeys = @{}
        foreach ($favId in $favProfiles) {
            if (-not $script:Profiles.Contains($favId)) { continue }
            $favoriteGroup = Get-GameGroup -ProfileId $favId
            if ([string]::IsNullOrWhiteSpace($favoriteGroup)) { continue }
            $favoriteGroupKey = "$favoriteGroup".Trim().ToLowerInvariant()
            if ($favoriteHeaderGroupKeys.ContainsKey($favoriteGroupKey)) { continue }
            $favoriteHeaderGroupKeys[$favoriteGroupKey] = $true
            if ($favoriteHeaderGameGroups.Count -lt 3) {
                [void]$favoriteHeaderGameGroups.Add($favoriteGroup)
            }
        }

        $favLabel = New-Object System.Windows.Forms.ToolStripMenuItem
        $favLabel.Text = "FAVORITES"
        $favLabel.Enabled = $false
        $favLabel.BackColor = $script:Colors.Background
        $favLabel.ForeColor = Get-TraySectionHeaderTint -Section "Favorites"
        $favLabel.Font = $script:FontSectionHeader
        Set-TraySectionHeaderVisualState `
            -Item $favLabel `
            -ChipText (Get-TraySectionHeaderSummaryChips `
                -ItemCount $favProfiles.Count `
                -ItemSingular "favorite" `
                -ItemPlural "favorites" `
                -GameCount $favoriteHeaderGroupKeys.Count)
        $favLabel.Image = $null
        $menu.Items.Add($favLabel) | Out-Null
        $script:favSectionLabel = $favLabel

        foreach ($favId in $favProfiles) {
            $p = $script:Profiles[$favId]
            $catColor = Get-CategoryColor -Category $p.Cat -Fallback $script:Colors.Text
            $gameColor = Get-TrayProfileMenuAccent -ProfileId $favId -Profile $p
            $item = New-Object System.Windows.Forms.ToolStripMenuItem
            $item.Text = Get-TrayProfileObjectDisplayName -Profile $p -Fallback $favId
            $item.Tag = $favId
            $item.Image = New-TrayProfileMenuImage `
                -ProfileId $favId `
                -IsActive ($favId -eq $script:activeProfile) `
                -ShowSyncBadge $true `
                -FavoriteBadge $true
            $item.BackColor = $script:Colors.Background
            $item.ForeColor = $gameColor
            $item.Font = $script:FontMenuRow
            Set-TrayProfileMenuItemMetadata -Item $item -ProfileId $favId -Profile $p
            $item.Add_Click({
                param($s, $ev)
                Apply-Profile $s.Tag
            }.GetNewClosure())
            Register-TrayProfileHoverPreview -Item $item -ProfileId $favId
            $menu.Items.Add($item) | Out-Null
            $script:profileMenuItems += $item
        }
    }

    # ─── RECENT ───

    $recentProfiles = @($script:TrayConfig.recentProfiles)
    if ($recentProfiles.Count -gt 0) {
        $recentHeaderGameGroups = [System.Collections.Generic.List[string]]::new()
        $recentHeaderGroupKeys = @{}
        $recentDisplayCount = 0
        foreach ($entry in $recentProfiles) {
            $rId = $entry.id
            if (-not $rId) { continue }
            if ($favProfiles -contains $rId) { continue }
            if (-not $script:Profiles.Contains($rId)) { continue }
            if ($recentDisplayCount -ge 3) { break }
            $recentDisplayCount += 1
            $recentGroup = Get-GameGroup -ProfileId $rId
            if ([string]::IsNullOrWhiteSpace($recentGroup)) { continue }
            $recentGroupKey = "$recentGroup".Trim().ToLowerInvariant()
            if ($recentHeaderGroupKeys.ContainsKey($recentGroupKey)) { continue }
            $recentHeaderGroupKeys[$recentGroupKey] = $true
            [void]$recentHeaderGameGroups.Add($recentGroup)
            if ($recentHeaderGameGroups.Count -ge 3) { break }
        }

        $recentLabel = New-Object System.Windows.Forms.ToolStripMenuItem
        $recentLabel.Text = "RECENT"
        $recentLabel.Enabled = $false
        $recentLabel.BackColor = $script:Colors.Background
        $recentLabel.ForeColor = Get-TraySectionHeaderTint -Section "Recent"
        $recentLabel.Font = $script:FontSectionHeader
        Set-TraySectionHeaderVisualState `
            -Item $recentLabel `
            -ChipText (Get-TraySectionHeaderSummaryChips `
                -ItemCount $recentDisplayCount `
                -ItemSingular "recent" `
                -ItemPlural "recent" `
                -GameCount $recentHeaderGameGroups.Count)
        $recentLabel.Image = $null
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
            $gameColor = Dim-Color -Color (Get-TrayProfileMenuAccent -ProfileId $rId -Profile $p) -Alpha 210
            $item = New-Object System.Windows.Forms.ToolStripMenuItem
            $item.Text = Get-TrayProfileObjectDisplayName -Profile $p -Fallback $rId
            $item.Tag = $rId
            $item.Image = New-TrayProfileMenuImage `
                -ProfileId $rId `
                -IsActive ($rId -eq $script:activeProfile) `
                -ShowSyncBadge $true
            $item.BackColor = $script:Colors.Background
            $item.ForeColor = $gameColor
            $item.Font = $script:FontMenuRow
            Set-TrayProfileMenuItemMetadata -Item $item -ProfileId $rId -Profile $p -ExtraChipText "RECENT"
            $item.Add_Click({
                param($s, $ev)
                Apply-Profile $s.Tag
            }.GetNewClosure())
            Register-TrayProfileHoverPreview -Item $item -ProfileId $rId
            $menu.Items.Add($item) | Out-Null
            $shownRecent++
        }
    }

    # ─── PROFILES (game submenus with sync badges) ───

    $menu.Items.Add((New-Object System.Windows.Forms.ToolStripSeparator)) | Out-Null

    $profilesHeaderGameGroups = [System.Collections.Generic.List[string]]::new()
    $profilesHeaderGroupKeys = @{}
    $profilesVisibleCount = 0
    foreach ($id in $script:Profiles.Keys) {
        $p = $script:Profiles[$id]
        if ($null -ne $p.TrayVisible -and -not [bool]$p.TrayVisible) { continue }
        $profilesVisibleCount += 1
        $profileHeaderGroup = Get-GameGroup -ProfileId $id
        if ([string]::IsNullOrWhiteSpace($profileHeaderGroup)) { continue }
        $profileHeaderGroupKey = "$profileHeaderGroup".Trim().ToLowerInvariant()
        if ($profilesHeaderGroupKeys.ContainsKey($profileHeaderGroupKey)) { continue }
        $profilesHeaderGroupKeys[$profileHeaderGroupKey] = $true
        if ($profilesHeaderGameGroups.Count -lt 3) {
            [void]$profilesHeaderGameGroups.Add($profileHeaderGroup)
        }
    }

    $profilesLabel = New-Object System.Windows.Forms.ToolStripMenuItem
    $profilesLabel.Text = "PROFILES"
    $profilesLabel.Enabled = $false
    $profilesLabel.BackColor = $script:Colors.BackgroundDark
    $profilesLabel.ForeColor = Get-TraySectionHeaderTint -Section "Profiles"
    $profilesLabel.Font = $script:FontSectionHeader
    Set-TraySectionHeaderVisualState `
        -Item $profilesLabel `
        -ChipText (Get-TraySectionHeaderSummaryChips `
            -ItemCount $profilesVisibleCount `
            -ItemSingular "profile" `
            -ItemPlural "profiles" `
            -GameCount $profilesHeaderGroupKeys.Count)
    $profilesLabel.Image = $null
    $menu.Items.Add($profilesLabel) | Out-Null

    # Helper to create a profile menu item (used in both direct items and submenus)
    function New-ProfileMenuItem {
        param([string]$ProfileId, [bool]$InSubmenu = $false, [bool]$ShowBadge = $false)
        $p = $script:Profiles[$ProfileId]
        $isFav = Test-Favorite -ProfileId $ProfileId -Config $script:TrayConfig
        $catColor = Get-CategoryColor -Category $p.Cat -Fallback $script:Colors.Text
        $gameColor = Get-TrayProfileMenuAccent -ProfileId $ProfileId -Profile $p

        $item = New-Object System.Windows.Forms.ToolStripMenuItem
        $item.Text = Get-ProfileMenuDisplayText -ProfileId $ProfileId -InSubmenu $InSubmenu
        $item.Image = New-TrayProfileMenuImage `
            -ProfileId $ProfileId `
            -IsActive ($ProfileId -eq $script:activeProfile) `
            -InSubmenu $InSubmenu `
            -ShowSyncBadge $ShowBadge `
            -FavoriteBadge $isFav

        $item.Tag = $ProfileId
        $item.BackColor = $script:Colors.Background
        $item.ForeColor = $gameColor
        $item.Font = $script:FontMenuRow

        Set-TrayProfileMenuItemMetadata -Item $item -ProfileId $ProfileId -Profile $p

        $item.Add_Click({
            param($s, $ev)
            Apply-Profile $s.Tag
        }.GetNewClosure())
        Register-TrayProfileHoverPreview -Item $item -ProfileId $ProfileId

        return $item
    }

    function New-GameFlyoutHeaderItem {
        param(
            [object]$GroupInfo,
            [string]$GameGroup,
            [string]$Category,
            [System.Drawing.Color]$CategoryColor,
            [int]$VariantCount,
            [string[]]$ProfileIds = @()
        )

        $gameColor = if (Get-Command Get-GameAccentColor -ErrorAction SilentlyContinue) {
            Get-GameAccentColor -GameGroup $GameGroup -FallbackColor $CategoryColor
        }
        else {
            $CategoryColor
        }
        $variantLabel = if ($VariantCount -eq 1) { "1 choice" } else { "$VariantCount choices" }
        $headerItem = New-Object System.Windows.Forms.ToolStripMenuItem
        $headerItem.Text = "$($GroupInfo.Name)  |  $variantLabel"
        $headerItem.Tag = "__game_flyout_header__"
        $headerItem.AccessibleName = "__game_flyout_header__"
        $headerItem.AccessibleDescription = Get-GameFlyoutHeaderSummaryChips -ProfileIds $ProfileIds
        $headerItem.Padding = New-Object System.Windows.Forms.Padding(0, 0, 76, 0)
        $headerItem.Enabled = $false
        $headerItem.BackColor = $script:Colors.BackgroundDark
        $headerItem.ForeColor = $gameColor
        $headerItem.Font = $script:FontEyebrow
        $headerItem.Image = New-TrayGameGroupMedallionBitmap -GameGroup $GameGroup -Color $gameColor -Category $Category
        $headerItem.ToolTipText = "Game group header for $($GroupInfo.Name): $variantLabel"
        return $headerItem
    }

    # Group visible profiles by category, then by game. Each game appears once;
    # SDR/HDR/sync/capture choices live under that game's flyout.
    $catGameGroups = [ordered]@{}

    foreach ($id in $script:Profiles.Keys) {
        $p = $script:Profiles[$id]
        if ($null -ne $p.TrayVisible -and -not [bool]$p.TrayVisible) { continue }
        $gameGroup = Get-GameGroup -ProfileId $id
        $cat = Normalize-TrayCategory -Category $p.Cat
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

    # Build category order dynamically: use preferred order for known
    # categories, append any user-defined categories alphabetically.
    $preferredMergedOrder = @("Desktop", "Fighting", "Shooters", "RPGs", "Other")
    $mergedCategoryOrder = @()
    foreach ($cat in $preferredMergedOrder) {
        if ($catGameGroups.Contains($cat)) { $mergedCategoryOrder += $cat }
    }
    foreach ($cat in ($catGameGroups.Keys | Sort-Object)) {
        if ($mergedCategoryOrder -notcontains $cat) { $mergedCategoryOrder += $cat }
    }

    foreach ($cat in $mergedCategoryOrder) {
        if (-not $catGameGroups.Contains($cat)) { continue }

        $catColor = if ($script:CategoryColors.ContainsKey($cat)) { $script:CategoryColors[$cat] } else { $script:Colors.Text }
        $catGameCount = @($catGameGroups[$cat].Keys).Count
        $catProfileCount = 0
        foreach ($gameGroupKey in $catGameGroups[$cat].Keys) {
            $catProfileCount += @($catGameGroups[$cat][$gameGroupKey]).Count
        }
        $catItem = New-Object System.Windows.Forms.ToolStripMenuItem
        $catItem.Text = $cat
        $catItem.Tag = $cat
        $catItem.AccessibleName = "__category_header__"
        $catItem.AccessibleDescription = ""
        $catItem.ToolTipText = Get-CategoryHeaderSummaryChips -GameCount $catGameCount -ProfileCount $catProfileCount
        # Match the section-header rhythm: bind the band downward to its rows.
        $catItem.Padding = New-Object System.Windows.Forms.Padding(0, 5, 0, 2)
        $catItem.Image = $null
        $catItem.Enabled = $false
        $catItem.BackColor = $script:Colors.Background
        $catItem.ForeColor = Get-TrayCategoryHeaderTint -Category $cat -CategoryColor $catColor
        $catItem.Font = $script:FontCategoryHeader
        $menu.Items.Add($catItem) | Out-Null
        $script:categoryHeaders += $catItem

        $groupInfos = @()
        foreach ($gameGroup in $catGameGroups[$cat].Keys) {
            $profileIds = @($catGameGroups[$cat][$gameGroup] | Sort-Object `
                @{ Expression = { if ($script:Profiles[$_].Rank) { [int]$script:Profiles[$_].Rank } else { 100 } } }, `
                @{ Expression = { Get-ProfileVariantLabel -ProfileId $_ } })
            if ($profileIds.Count -eq 0) { continue }
            $firstId = $profileIds[0]
            $firstRank = if ($script:Profiles[$firstId].Rank) { [int]$script:Profiles[$firstId].Rank } else { 100 }
            $groupInfos += [pscustomobject]@{
                Key = $gameGroup
                Name = Get-GameGroupName -ProfileId $firstId
                Rank = $firstRank
                ProfileIds = $profileIds
            }
        }

        foreach ($groupInfo in ($groupInfos | Sort-Object Rank, Name)) {
            $profileIds = @($groupInfo.ProfileIds)
            $gameGroup = $groupInfo.Key

            if ($profileIds.Count -eq 1) {
                # Single profile — show directly with optional sync badge
                $item = New-ProfileMenuItem -ProfileId $profileIds[0] -ShowBadge $true
                $menu.Items.Add($item) | Out-Null
                $script:profileMenuItems += $item
            }
            else {
                # Multiple profiles — create a flyout submenu
                $submenuItem = New-Object System.Windows.Forms.ToolStripMenuItem
                $submenuItem.Text = $groupInfo.Name
                $submenuItem.Tag = $cat
                $submenuGameColor = if (Get-Command Get-GameAccentColor -ErrorAction SilentlyContinue) {
                    Get-GameAccentColor -GameGroup $gameGroup -FallbackColor $catColor
                }
                else {
                    $catColor
                }
                $submenuItem.Image = New-TrayGameGroupMedallionBitmap -GameGroup $gameGroup -Color $submenuGameColor -Category $cat
                $submenuItem.BackColor = $script:Colors.Background
                $submenuItem.ForeColor = $submenuGameColor
                $submenuItem.Font = $script:FontMenuRowBold
                $profileVariantChip = ""
                $submenuItem.ToolTipText = "Open profile choices for $($groupInfo.Name): $($profileIds.Count)"
                Set-TrayGameGroupRowVisualState -Item $submenuItem

                $flyoutHeader = New-GameFlyoutHeaderItem `
                    -GroupInfo $groupInfo `
                    -GameGroup $gameGroup `
                    -Category $cat `
                    -CategoryColor $catColor `
                    -VariantCount $profileIds.Count `
                    -ProfileIds $profileIds
                $submenuItem.DropDownItems.Add($flyoutHeader) | Out-Null
                $submenuItem.DropDownItems.Add((New-Object System.Windows.Forms.ToolStripSeparator)) | Out-Null

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

    # ─── ACTIONS (flyout submenu) ───

    $menu.Items.Add((New-Object System.Windows.Forms.ToolStripSeparator)) | Out-Null

    $actionsMenu = New-Object System.Windows.Forms.ToolStripMenuItem
    $actionsMenu.Text = "Actions"
    $actionsMenu.BackColor = $script:Colors.Background
    $actionsMenu.ForeColor = $script:Colors.AccentAmber
    $actionsMenu.Font = $script:FontMenuRowBold
    $actionsMenu.Image = New-ActionBitmap -Action "Actions" -Color $script:Colors.AccentAmber
    $actionsMenu.AccessibleName = "__flyout_command__"
    $actionsMenu.AccessibleDescription = "TOOLS"
    $actionsMenu.Padding = New-Object System.Windows.Forms.Padding(0, 0, 56, 0)

    # Restore Previous
    $script:restoreItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $script:restoreItem.Text = "Restore Previous Settings"
    $script:restoreItem.Enabled = $false
    $script:restoreItem.BackColor = $script:Colors.Background
    $script:restoreItem.ForeColor = $script:Colors.AccentAmber
    $script:restoreItem.Font = $script:FontMenuRow
    $script:restoreItem.Image = New-ActionBitmap -Action "Restore" -Color $script:Colors.AccentAmber
    $script:restoreItem.ToolTipText = "Restore the last backup before profile was applied"
    Set-TrayCommandItemVisualState -Item $script:restoreItem -ChipText "RESTORE"
    $script:restoreItem.Add_Click({ Restore-Settings })
    $actionsMenu.DropDownItems.Add($script:restoreItem) | Out-Null

    # Run Audit
    $auditItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $auditItem.Text = "Run System Audit"
    $auditItem.BackColor = $script:Colors.Background
    $auditItem.ForeColor = $script:Colors.AccentBlue
    $auditItem.Font = $script:FontMenuRow
    $auditItem.Image = New-ActionBitmap -Action "Audit" -Color $script:Colors.AccentBlue
    $auditItem.ToolTipText = "Scan the current audit scope for optimization issues"
    Set-TrayCommandItemVisualState -Item $auditItem -ChipText "AUDIT"
    $auditItem.Add_Click({ Run-Audit })
    $actionsMenu.DropDownItems.Add($auditItem) | Out-Null

    # Apply Pending Fixes - targeted verifier remediation, not a full profile apply.
    $script:applyPendingItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $script:applyPendingItem.Text = "Apply Pending Fixes"
    $script:applyPendingItem.Enabled = $false
    $script:applyPendingItem.Visible = $false
    $script:applyPendingItem.BackColor = $script:Colors.Background
    $script:applyPendingItem.ForeColor = $script:Colors.AccentAmber
    $script:applyPendingItem.Font = $script:FontMenuRow
    $script:applyPendingItem.Image = New-ActionBitmap -Action "PendingFix" -Color $script:Colors.TextDisabled
    $script:applyPendingItem.ToolTipText = "No verifier-reported pending fixes for the active profile"
    Set-TrayCommandItemVisualState -Item $script:applyPendingItem -ChipText "FIX"
    $script:applyPendingItem.Add_Click({ Apply-PendingProfileFixes })
    $actionsMenu.DropDownItems.Add($script:applyPendingItem) | Out-Null

    # Reset Display Pipeline - manual graphics-driver reset. Profile apply
    # does not run disruptive display recovery automatically; this menu item
    # is the explicit stale-color recovery action and requires confirmation.
    $resetDisplayItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $resetDisplayItem.Text = "Reset Display Pipeline..."
    $resetDisplayItem.BackColor = $script:Colors.Background
    $resetDisplayItem.ForeColor = $script:Colors.AccentAmber
    $resetDisplayItem.Font = $script:FontMenuRow
    $resetDisplayItem.Image = New-ActionBitmap -Action "Reset" -Color $script:Colors.AccentAmber
    $resetDisplayItem.ToolTipText = "Advanced recovery: sends Ctrl+Win+Shift+B x2 and may blank monitors for a few seconds."
    Set-TrayCommandItemVisualState -Item $resetDisplayItem -ChipText "RESET"
    $resetDisplayItem.Add_Click({
        Write-TrayLog "User invoked Reset Display Pipeline from tray menu"
        $confirm = [System.Windows.Forms.MessageBox]::Show(
            "This sends Ctrl+Win+Shift+B twice and can blank or disconnect monitors for a few seconds.`n`nUse only for explicit live display recovery, not routine profile verification.`n`nContinue?",
            "computa Display Pipeline Reset",
            [System.Windows.Forms.MessageBoxButtons]::YesNo,
            [System.Windows.Forms.MessageBoxIcon]::Warning,
            [System.Windows.Forms.MessageBoxDefaultButton]::Button2
        )
        if ($confirm -ne [System.Windows.Forms.DialogResult]::Yes) {
            Write-TrayLog "User cancelled Reset Display Pipeline from confirmation dialog"
            return
        }
        try {
            $tf = [System.IO.Path]::GetTempFileName()
            $errFile = "$tf.err"
            $proc = $null
            $proc = Start-Process -FilePath $script:PythonExe `
                -ArgumentList (Get-AbsoBackendArgs -CommandArgs @("reset-display", "--method", "driver-hotkey", "--json")) `
                -NoNewWindow -PassThru -WorkingDirectory $script:ProjectRoot `
                -RedirectStandardOutput $tf -RedirectStandardError $errFile
            # PS 5.1: cache the handle now or .ExitCode reads $null after exit.
            if ($proc) { $null = $proc.Handle }

            $completed = $proc.WaitForExit(30000)
            if (-not $completed) {
                try { $proc.Kill() } catch {}
                try { $proc.Dispose() } catch {}
                $proc = $null
                Write-TrayLog "Reset Display timed out after 30s" -Level "ERROR"
                Show-Notification -Title "computa" `
                    -Message "Display reset timed out after 30s" -Type "Error" `
                    -ActionName "Reset" -ActionColor $script:Colors.AccentAmber
                Set-TrayLastAction -Message "Display reset timed out after 30s"
                Update-MenuState
                return
            }

            $exitCode = $proc.ExitCode
            try { $proc.Dispose() } catch {}
            $proc = $null
            $out = Get-Content $tf -Raw -ErrorAction SilentlyContinue
            $errOutput = Get-Content $errFile -Raw -ErrorAction SilentlyContinue
            if ($errOutput) { Write-TrayLog "Reset Display CLI stderr: $errOutput" -Level "WARN" }
            if ($out) {
                $j = Invoke-JsonSafe -Text $out -Source 'ResetDisplay'
                $result = $null
                if ($null -ne $j -and $j.data -and $j.data.result) {
                    $result = $j.data.result
                }
                elseif ($null -ne $j -and $j.result) {
                    $result = $j.result
                }
                $exitCodeOk = ($null -eq $exitCode -or $exitCode -eq 0)
                if ($exitCodeOk -and $null -ne $j -and $j.success -and $j.data -and $j.data.success -and $null -ne $result) {
                    $count = $result.sent_count
                    if (-not $count) { $count = 0 }
                    Show-Notification -Title "computa" `
                        -Message "Display pipeline reset ($count combo(s) sent)" -Type "Success" `
                        -ActionName "Reset" -ActionColor $script:Colors.AccentAmber
                    Set-TrayLastAction -Message "Display reset: $count combo(s) sent"
                    Update-MenuState
                }
                elseif ($null -eq $j) {
                    Write-TrayLog "Reset Display: CLI produced unparseable JSON" -Level "ERROR"
                    Show-Notification -Title "computa" `
                        -Message "Display reset failed: runtime status unreadable. See tray log." -Type "Error" `
                        -ActionName "Reset" -ActionColor $script:Colors.AccentAmber
                    Set-TrayLastAction -Message "Display reset failed: runtime status unreadable"
                    Update-MenuState
                }
                else {
                    $err = if ($j.error) { $j.error } elseif ($j.data -and $j.data.result -and $j.data.result.error) { $j.data.result.error } elseif ($null -ne $exitCode -and $exitCode -ne 0) { "runtime exit code $exitCode" } else { "runtime error not reported" }
                    Write-TrayLog "Reset Display reported failure: $err" -Level "ERROR"
                    Show-Notification -Title "computa" `
                        -Message "Display reset failed: $err" -Type "Error" `
                        -ActionName "Reset" -ActionColor $script:Colors.AccentAmber
                    Set-TrayLastAction -Message "Display reset failed: $err"
                    Update-MenuState
                }
            }
            else {
                Write-TrayLog "Reset Display: CLI produced no output" -Level "ERROR"
                Show-Notification -Title "computa" `
                    -Message "Display reset failed: runtime returned no status" -Type "Error" `
                    -ActionName "Reset" -ActionColor $script:Colors.AccentAmber
                Set-TrayLastAction -Message "Display reset failed: runtime returned no status"
                Update-MenuState
            }
        }
        catch {
            Write-TrayLog "Reset Display threw: $($_.Exception.Message)" -Level "ERROR"
            Show-Notification -Title "computa" `
                -Message "Display reset failed: $($_.Exception.Message)" -Type "Error" `
                -ActionName "Reset" -ActionColor $script:Colors.AccentAmber
            Set-TrayLastAction -Message "Display reset failed: $($_.Exception.Message)"
            Update-MenuState
        }
        finally {
            if ($proc) {
                try { if (-not $proc.HasExited) { $proc.Kill() } } catch {}
                try { $proc.Dispose() } catch {}
            }
            if ($tf) { Remove-Item $tf -Force -ErrorAction SilentlyContinue }
            if ($errFile) { Remove-Item $errFile -Force -ErrorAction SilentlyContinue }
        }
    })
    $actionsMenu.DropDownItems.Add($resetDisplayItem) | Out-Null

    # Backups submenu (nested inside Actions)
    $backupTime = Get-LastBackupTime
    $recentBackups = Get-RecentBackups -Count 5
    $backupHeaderGameGroups = [System.Collections.Generic.List[string]]::new()
    $backupHeaderGroupKeys = @{}
    foreach ($backup in @($recentBackups)) {
        $backupProfileId = if ($backup.ProfileId) { "$($backup.ProfileId)" } else { "" }
        if ([string]::IsNullOrWhiteSpace($backupProfileId)) { continue }
        # Manifest profile ids are still useful when the live catalog is stale.
        $backupGroup = Get-GameGroup -ProfileId $backupProfileId
        if ([string]::IsNullOrWhiteSpace($backupGroup)) { continue }
        $backupGroupKey = "$backupGroup".Trim().ToLowerInvariant()
        if ($backupHeaderGroupKeys.ContainsKey($backupGroupKey)) { continue }
        $backupHeaderGroupKeys[$backupGroupKey] = $true
        [void]$backupHeaderGameGroups.Add($backupGroup)
        if ($backupHeaderGameGroups.Count -ge 3) { break }
    }

    $backupsItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $backupsItem.Text = "Backups ($backupTime)"
    $backupsItem.BackColor = $script:Colors.Background
    $backupsItem.ForeColor = $script:Colors.AccentPurple
    $backupsItem.Font = $script:FontMenuRowBold
    if ($backupHeaderGameGroups.Count -gt 0 -and (Get-Command New-BackupGameMosaicBitmap -ErrorAction SilentlyContinue)) {
        $backupsItem.Image = New-BackupGameMosaicBitmap -GameGroups @($backupHeaderGameGroups) -Color $script:Colors.AccentPurple -Category "Other"
    }
    else {
        $backupsItem.Image = New-ActionBitmap -Action "Backups" -Color $script:Colors.AccentPurple
    }
    $backupsItem.ToolTipText = if ($backupTime -eq "Never") {
        "No backups found. Applying a profile creates a restorable backup."
    } else {
        "Recent backups available. Open this submenu to restore one."
    }
    Set-TrayCommandItemVisualState -Item $backupsItem -ChipText (Get-BackupMenuChipText -VisibleBackupCount @($recentBackups).Count)

    $openBackupsItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $openBackupsItem.Text = "Open Backups Folder"
    $openBackupsItem.BackColor = $script:Colors.Background
    $openBackupsItem.ForeColor = $script:Colors.Text
    $openBackupsItem.Font = $script:FontMenuRow
    $openBackupsItem.Image = New-ActionBitmap -Action "Folder" -Color $script:Colors.AccentPurple
    $openBackupsItem.ToolTipText = "Open the current backups folder"
    Set-TrayCommandItemVisualState -Item $openBackupsItem -ChipText "FOLDER"
    $openBackupsItem.Add_Click({ Open-BackupsFolder })
    $backupsItem.DropDownItems.Add($openBackupsItem) | Out-Null

    $backupsItem.DropDownItems.Add((New-Object System.Windows.Forms.ToolStripSeparator)) | Out-Null

    if (@($recentBackups).Count -le 0) {
        $noBackupsItem = New-Object System.Windows.Forms.ToolStripMenuItem
        $noBackupsItem.Text = "No backups found"
        $noBackupsItem.Enabled = $false
        $noBackupsItem.BackColor = $script:Colors.BackgroundDark
        $noBackupsItem.ForeColor = $script:Colors.TextDisabled
        $noBackupsItem.Font = $script:FontMenuRow
        $noBackupsItem.Image = New-ActionBitmap -Action "Backups" -Color $script:Colors.TextDisabled
        $noBackupsItem.ToolTipText = "No backup folders were found in installed or workspace backup locations."
        $backupsItem.DropDownItems.Add($noBackupsItem) | Out-Null
    }

    foreach ($backup in $recentBackups) {
        $bItem = New-Object System.Windows.Forms.ToolStripMenuItem
        $bItem.Text = $backup.Label
        $bItem.Tag = $backup.Name
        $bItem.BackColor = $script:Colors.Background
        $bItem.ForeColor = $script:Colors.TextDim
        $bItem.Font = $script:FontMono
        $bItem.AccessibleName = "__backup_menu_item__"
        $bItem.AccessibleDescription = Get-BackupSourceChipText -Source $backup.Source
        $bItem.Padding = New-Object System.Windows.Forms.Padding(0, 0, 70, 0)
        $backupProfileId = if ($backup.ProfileId) { "$($backup.ProfileId)" } else { "" }
        $backupProfile = $null
        if (-not [string]::IsNullOrWhiteSpace($backupProfileId)) {
            if ($script:Profiles -and $script:Profiles.Contains($backupProfileId)) {
                $backupProfile = $script:Profiles[$backupProfileId]
            }
            $backupFavoriteBadge = if (Get-Command Test-Favorite -ErrorAction SilentlyContinue) {
                Test-Favorite -ProfileId $backupProfileId -Config $script:TrayConfig
            }
            else {
                $false
            }
            $bItem.Image = New-TrayProfileMenuImage `
                -ProfileId $backupProfileId `
                -ShowSyncBadge $true `
                -FavoriteBadge $backupFavoriteBadge
            $bItem.ForeColor = Get-TrayProfileAccentColor -ProfileId $backupProfileId -Profile $backupProfile -Fallback $script:Colors.TextDim
        }
        else {
            $bItem.Image = New-ActionBitmap -Action "Restore" -Color $script:Colors.AccentPurple
        }
        $bItem.ToolTipText = "Restore backup: $($backup.Label)`nSource: $($backup.SourceLabel)"
        $capturedName = $backup.Name
        $capturedLabel = $backup.Label
        $capturedProfileId = $backupProfileId
        $bItem.Add_Click({
            Set-TrayOperationTooltipText -Text "computa - Restoring..."
            $restoreProfile = $null
            if (
                -not [string]::IsNullOrWhiteSpace($capturedProfileId) -and
                $script:Profiles -and
                $script:Profiles.Contains($capturedProfileId)
            ) {
                $restoreProfile = $script:Profiles[$capturedProfileId]
            }
            $restoreVisual = Get-TrayProfileToastVisualArgs -ProfileId $capturedProfileId -Profile $restoreProfile
            $restoreTitle = if (-not [string]::IsNullOrWhiteSpace($capturedProfileId)) { Get-TrayProfileDisplayName -ProfileId $capturedProfileId } else { "computa" }
            $restoreMetaText = if (-not [string]::IsNullOrWhiteSpace($capturedProfileId)) { $capturedProfileId } else { $capturedName }
            try {
                $tf = [System.IO.Path]::GetTempFileName()
                $errFile = "$tf.err"
                $proc = Start-Process -FilePath $script:PythonExe -ArgumentList (Get-AbsoBackendArgs -CommandArgs @("restore", $capturedName, "--json")) `
                    -NoNewWindow -PassThru -WorkingDirectory $script:ProjectRoot `
                    -RedirectStandardOutput $tf -RedirectStandardError $errFile
                # PS 5.1: cache the handle now or .ExitCode reads $null after exit.
                if ($proc) { $null = $proc.Handle }
                $completed = $proc.WaitForExit(120000)
                if (-not $completed -or -not $proc.HasExited) {
                    try { $proc.Kill() } catch {}
                    try { $proc.Dispose() } catch {}
                    Remove-Item $tf -Force -ErrorAction SilentlyContinue
                    Remove-Item $errFile -Force -ErrorAction SilentlyContinue
                    Write-TrayLog "Restore '$capturedName' timed out after 120s" -Level "ERROR"
                    Show-Notification @restoreVisual -Title $restoreTitle -Message "Restore timed out: $capturedLabel" -Type "Error" -MetaText $restoreMetaText
                    Set-TrayLastAction -Message "Restore timed out: $capturedLabel"
                    Update-MenuState
                    return
                }
                $exitCode = $proc.ExitCode
                $proc.Dispose()
                $out = Get-Content $tf -Raw -ErrorAction SilentlyContinue
                $errOutput = Get-Content $errFile -Raw -ErrorAction SilentlyContinue
                if ($errOutput) { Write-TrayLog "Restore '$capturedName' stderr: $errOutput" -Level "WARN" }
                Remove-Item $tf -Force -ErrorAction SilentlyContinue
                Remove-Item $errFile -Force -ErrorAction SilentlyContinue
                if ($out) {
                    $j = Invoke-JsonSafe -Text $out -Source 'RestoreBackup'
                    $exitCodeOk = ($null -eq $exitCode -or $exitCode -eq 0)
                    if ($exitCodeOk -and $null -ne $j -and $j.success -and $j.data -and $j.data.success) {
                        Show-Notification @restoreVisual -Title $restoreTitle -Message "Restored from: $capturedLabel" -Type "Success" -MetaText $restoreMetaText
                        $script:activeProfile = $null
                        Reset-ActiveProfileVerificationState
                        Set-TrayLastAction -Message "Restored backup: $capturedLabel"
                        $script:TrayConfig = Set-LastProfileState -Config $script:TrayConfig -Status "restored" -Source "tray_restore_backup"
                        Set-IconState -State "Idle"
                        Update-MenuState
                    }
                    elseif ($null -eq $j) {
                        Write-TrayLog "Restore '$capturedName': CLI produced unparseable JSON" -Level "ERROR"
                        Show-Notification @restoreVisual -Title $restoreTitle -Message "Restore failed: runtime status unreadable. See tray log." -Type "Error" -MetaText $restoreMetaText
                        Set-TrayLastAction -Message "Restore failed: runtime status unreadable"
                        Update-MenuState
                    }
                    else {
                        $restoreErr = if ($j.error) { $j.error } elseif ($j.data -and $j.data.error) { $j.data.error } elseif ($j.data -and $j.data.message) { $j.data.message } elseif ($null -ne $exitCode -and $exitCode -ne 0) { "runtime exit code $exitCode" } else { "runtime error not reported" }
                        Write-TrayLog "Restore '$capturedName' reported failure: $restoreErr" -Level "ERROR"
                        Show-Notification @restoreVisual -Title $restoreTitle -Message "Restore failed: $restoreErr" -Type "Error" -MetaText $restoreMetaText
                        Set-TrayLastAction -Message "Restore failed: $restoreErr"
                        Update-MenuState
                    }
                } else {
                    Write-TrayLog "Restore '$capturedName': CLI produced no output" -Level "ERROR"
                    Show-Notification @restoreVisual -Title $restoreTitle -Message "Restore failed: runtime returned no status" -Type "Error" -MetaText $restoreMetaText
                    Set-TrayLastAction -Message "Restore failed: runtime returned no status"
                    Update-MenuState
                }
            } catch {
                Write-TrayLog "Restore '$capturedName' threw: $($_.Exception.Message)" -Level "ERROR"
                Show-Notification @restoreVisual -Title $restoreTitle -Message "Restore failed: $($_.Exception.Message)" -Type "Error" -MetaText $restoreMetaText
                Set-TrayLastAction -Message "Restore failed: $($_.Exception.Message)"
                Update-MenuState
            } finally {
                if ($tf) { Remove-Item $tf -Force -ErrorAction SilentlyContinue }
                if ($errFile) { Remove-Item $errFile -Force -ErrorAction SilentlyContinue }
                Restore-TrayTooltipFromState
            }
        }.GetNewClosure())
        $backupsItem.DropDownItems.Add($bItem) | Out-Null
    }

    $actionsMenu.DropDownItems.Add($backupsItem) | Out-Null

    $actionsMenu.DropDownItems.Add((New-Object System.Windows.Forms.ToolStripSeparator)) | Out-Null

    # Toggle Quick Panel
    $quickPanelItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $quickPanelIsVisible = [bool](
        $script:QuickPanelVisible -and
        $script:QuickPanelForm -and
        -not $script:QuickPanelForm.IsDisposed
    )
    $quickPanelItem.Text = if ($quickPanelIsVisible) { "Close Quick Panel" } else { "Open Quick Panel" }
    $quickPanelItem.BackColor = $script:Colors.Background
    $quickPanelItem.ForeColor = $script:Colors.AccentGreen
    $quickPanelItem.Font = $script:FontMenuRow
    $quickPanelItem.Image = New-ActionBitmap -Action "QuickPanel" -Color $script:Colors.AccentGreen
    $quickPanelItem.ToolTipText = if ($quickPanelIsVisible) {
        "Close the visible floating quick-access panel"
    }
    else {
        "Open the floating quick-access panel; empty/profile-missing states are shown in the panel"
    }
    $quickPanelItem.Checked = $quickPanelIsVisible
    Set-TrayCommandItemVisualState -Item $quickPanelItem -ChipText "PANEL"
    $quickPanelItem.Add_Click({
        if ($script:QuickPanelVisible) {
            Close-QuickPanel
            $script:TrayConfig.showQuickPanel = $false
            Set-TrayLastAction -Message "Quick Panel closed"
            Update-MenuState
        }
        else {
            $quickPanelEmpty = Get-QuickPanelEmptyStatus
            $quickPanelPendingApplyText = Get-ActiveProfilePendingApplyText
            $quickPanelWindowsRestartText = Get-ActiveProfileRebootPendingText
            $quickPanelVerificationText = Get-ActiveProfileVerificationInProgressText
            Show-QuickPanel -Favorites $script:TrayConfig.favorites -Profiles $script:Profiles -ActiveProfile $script:activeProfile -ActivePendingApplyText $quickPanelPendingApplyText -ActiveWindowsRestartText $quickPanelWindowsRestartText -ActiveVerificationText $quickPanelVerificationText -EmptyMessage $quickPanelEmpty.Message -EmptyProfileId $quickPanelEmpty.ProfileId -OnApply { param($id) Apply-Profile $id }
            $script:TrayConfig.showQuickPanel = [bool]$script:QuickPanelVisible
            if (-not $script:QuickPanelVisible) {
                if (-not [string]::IsNullOrWhiteSpace($quickPanelEmpty.ProfileId)) {
                    $quickPanelEmptyVisual = Get-TrayProfileToastVisualArgs -ProfileId $quickPanelEmpty.ProfileId -Profile $null
                    $quickPanelEmptyTitle = Get-TrayProfileDisplayName -ProfileId $quickPanelEmpty.ProfileId
                    Show-Notification @quickPanelEmptyVisual -Title $quickPanelEmptyTitle -Message $quickPanelEmpty.Message -Type "Info" -MetaText $quickPanelEmpty.ProfileId
                }
                else {
                    Show-Notification -Title "computa Quick Panel" -Message $quickPanelEmpty.Message -Type "Info" -ActionName "QuickPanel" -ActionColor $script:Colors.AccentBlue
                }
                Set-TrayLastAction -Message $quickPanelEmpty.LastAction
            }
            elseif ($script:QuickPanelEmptyState) {
                Set-TrayLastAction -Message $quickPanelEmpty.LastAction
            }
            else {
                Set-TrayLastAction -Message "Quick Panel opened"
            }
            Update-MenuState
        }
        $quickPanelItem.Checked = [bool]$script:QuickPanelVisible
        $quickPanelItem.Text = if ($script:QuickPanelVisible) { "Close Quick Panel" } else { "Open Quick Panel" }
        Save-TrayConfig $script:TrayConfig
    })
    $actionsMenu.DropDownItems.Add($quickPanelItem) | Out-Null

    $actionsMenu.DropDownItems.Add((New-Object System.Windows.Forms.ToolStripSeparator)) | Out-Null

    # Refresh Profiles
    $refreshProfilesItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $refreshProfilesItem.Text = "Refresh Profiles"
    $refreshProfilesItem.BackColor = $script:Colors.Background
    $refreshProfilesItem.ForeColor = $script:Colors.AccentBlue
    $refreshProfilesItem.Font = $script:FontMenuRow
    $refreshProfilesItem.Image = New-ActionBitmap -Action "Refresh" -Color $script:Colors.AccentBlue
    $refreshProfilesItem.ToolTipText = "Reload the profile list and user profiles; no profile is applied."
    Set-TrayCommandItemVisualState -Item $refreshProfilesItem -ChipText "REFRESH"
    $refreshProfilesItem.Add_Click({
        try {
            Initialize-ProfilesFromCliCatalog
            $profileCount = if ($script:Profiles) { $script:Profiles.Count } else { 0 }
            $catalogSource = if ($script:ProfileCatalogLastSource) { "$($script:ProfileCatalogLastSource)" } else { "source not reported" }
            if ($profileCount -le 0) {
                Show-Notification -Title "computa" -Message "Profile refresh failed: no profiles loaded" -Type "Error" -ActionName "Refresh" -ActionColor $script:Colors.AccentBlue
                Write-TrayLog "Profile refresh via menu loaded zero profiles" -Level "ERROR"
                Set-TrayLastAction -Message "Profile refresh failed: no profiles loaded"
            }
            elseif ($script:ProfileCatalogUsedFallback) {
                Show-Notification -Title "computa" -Message "Profiles loaded from built-in fallback profile list ($profileCount profiles)" -Type "Warning" -ActionName "Refresh" -ActionColor $script:Colors.AccentBlue
                Write-TrayLog "Profiles refreshed via menu from built-in fallback ($profileCount profiles)" -Level "WARN"
                Set-TrayLastAction -Message "Profiles fallback list loaded: $profileCount"
            }
            else {
                Show-Notification -Title "computa" -Message "Profiles refreshed from $catalogSource ($profileCount profiles loaded)" -Type "Success" -ActionName "Refresh" -ActionColor $script:Colors.AccentBlue
                Write-TrayLog "Profiles refreshed via menu from $catalogSource ($profileCount profiles)"
                Set-TrayLastAction -Message "Profiles refreshed: $profileCount from $catalogSource"
            }
            Update-MenuState
        }
        catch {
            Write-TrayLog "Failed to refresh profiles: $($_.Exception.Message)" -Level "ERROR"
            Show-Notification -Title "computa" -Message "Profile refresh failed: $($_.Exception.Message)" -Type "Error" -ActionName "Refresh" -ActionColor $script:Colors.AccentBlue
            Set-TrayLastAction -Message "Profile refresh failed: $($_.Exception.Message)"
            Update-MenuState
        }
    })
    $actionsMenu.DropDownItems.Add($refreshProfilesItem) | Out-Null

    # Open Profiles Folder
    $openProfilesItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $openProfilesItem.Text = "Open Profiles Folder"
    $openProfilesItem.BackColor = $script:Colors.Background
    $openProfilesItem.ForeColor = $script:Colors.TextDim
    $openProfilesItem.Font = $script:FontMenuRow
    $openProfilesItem.Image = New-ActionBitmap -Action "Folder" -Color $script:Colors.TextDim
    $openProfilesItem.ToolTipText = "Open user profiles folder in Explorer"
    Set-TrayCommandItemVisualState -Item $openProfilesItem -ChipText "FOLDER"
    $openProfilesItem.Add_Click({ Open-ProfilesFolder })
    $actionsMenu.DropDownItems.Add($openProfilesItem) | Out-Null

    $actionsMenu.DropDownItems.Add((New-Object System.Windows.Forms.ToolStripSeparator)) | Out-Null

    # Clear Standby List - memory-cache cleanup without touching profiles.
    $clearMemoryItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $clearMemoryItem.Text = "Clear Standby List"
    $clearMemoryItem.BackColor = $script:Colors.Background
    $clearMemoryItem.ForeColor = $script:Colors.AccentBlue
    $clearMemoryItem.Font = $script:FontMenuRow
    $clearMemoryItem.Image = New-ActionBitmap -Action "Memory" -Color $script:Colors.AccentBlue
    $clearMemoryItem.ToolTipText = "Requests a standby-memory purge; does not close apps or change profiles"
    Set-TrayCommandItemVisualState -Item $clearMemoryItem -ChipText "MEMORY"
    $clearMemoryItem.Add_Click({
        try {
            Write-TrayLog "Clearing standby list..."
            Set-TrayLastAction -Message "Clearing standby list"
            Update-MenuState
            $tempFile = [System.IO.Path]::GetTempFileName()
            $proc = Start-Process -FilePath $script:PythonExe `
                -ArgumentList (Get-AbsoBackendArgs -CommandArgs @("memory-clear", "--json")) `
                -NoNewWindow -PassThru -WorkingDirectory $script:ProjectRoot `
                -RedirectStandardOutput $tempFile
            # PS 5.1: cache the handle now or .ExitCode reads $null after exit.
            if ($proc) { $null = $proc.Handle }
            $completed = $proc.WaitForExit(15000)
            if (-not $completed -or -not $proc.HasExited) {
                $proc.Kill()
                $proc.Dispose()
                Remove-Item $tempFile -Force -ErrorAction SilentlyContinue
                Show-Notification -Title "computa" -Message "Standby clear timed out after 15s" -Type "Error" -ActionName "Memory" -ActionColor $script:Colors.AccentBlue
                Set-TrayLastAction -Message "Standby clear timed out after 15s"
                Update-MenuState
                return
            }
            $proc.Dispose()
            $raw = Get-Content $tempFile -Raw -ErrorAction SilentlyContinue
            Remove-Item $tempFile -Force -ErrorAction SilentlyContinue
            if (-not $raw) {
                Show-Notification -Title "computa" -Message "Standby clear failed: runtime returned no status" -Type "Error" -ActionName "Memory" -ActionColor $script:Colors.AccentBlue
                Set-TrayLastAction -Message "Standby clear failed: runtime returned no status"
                Update-MenuState
                return
            }
            $json = $raw | ConvertFrom-Json
            if ($json.success -and $json.data) {
                $freed = $json.data.freed_mb
                Show-Notification -Title "computa" -Message "Standby list cleared. Freed ~${freed}MB" -Type "Success" -ActionName "Memory" -ActionColor $script:Colors.AccentBlue
                Write-TrayLog "Standby list cleared: freed ${freed}MB"
                Set-TrayLastAction -Message "Standby list cleared: ~${freed}MB"
                Update-MenuState
            } else {
                $clearError = if ($json.error) { "$($json.error)" } elseif ($json.data -and $json.data.error) { "$($json.data.error)" } else { "runtime error not reported" }
                Show-Notification -Title "computa" -Message "Standby clear failed: $clearError" -Type "Error" -ActionName "Memory" -ActionColor $script:Colors.AccentBlue
                Set-TrayLastAction -Message "Standby clear failed: $clearError"
                Update-MenuState
            }
        } catch {
            Write-TrayLog "Clear standby failed: $($_.Exception.Message)" -Level "ERROR"
            Show-Notification -Title "computa" -Message "Standby clear failed: $($_.Exception.Message)" -Type "Error" -ActionName "Memory" -ActionColor $script:Colors.AccentBlue
            Set-TrayLastAction -Message "Standby clear failed: $($_.Exception.Message)"
            Update-MenuState
        }
    })
    $actionsMenu.DropDownItems.Add($clearMemoryItem) | Out-Null

    $menu.Items.Add($actionsMenu) | Out-Null

    # ─── SETTINGS (flyout submenu) ───

    $settingsMenu = New-Object System.Windows.Forms.ToolStripMenuItem
    $settingsMenu.Text = "Settings"
    $settingsMenu.BackColor = $script:Colors.Background
    $settingsMenu.ForeColor = $script:Colors.Text
    $settingsMenu.Font = $script:FontMenuRowBold
    $settingsMenu.Image = New-ActionBitmap -Action "Settings" -Color $script:Colors.Text
    $settingsMenu.AccessibleName = "__flyout_command__"
    $settingsMenu.AccessibleDescription = "PREFS"
    $settingsMenu.Padding = New-Object System.Windows.Forms.Padding(0, 0, 56, 0)

    # Auto-Start toggle
    $startupStatus = Get-StartupStatus
    $script:startupItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $script:startupItem.BackColor = $script:Colors.Background
    $script:startupItem.ForeColor = $script:Colors.Text
    $script:startupItem.Font = $script:FontMenuRow
    Set-StartupMenuState -StartupStatus $startupStatus
    $script:startupItem.Add_Click({ Toggle-Startup })
    $settingsMenu.DropDownItems.Add($script:startupItem) | Out-Null

    # Notifications toggle
    $script:notifyToggle = New-Object System.Windows.Forms.ToolStripMenuItem
    $script:notifyToggle.Text = "Toast Popups"
    $script:notifyToggle.Checked = $script:EnableBalloonNotifications
    $script:notifyToggle.BackColor = $script:Colors.Background
    $script:notifyToggle.ForeColor = $script:Colors.Text
    $script:notifyToggle.Font = $script:FontMenuRow
    $script:notifyToggle.Image = New-ActionBitmap -Action "Toast" -Color $script:Colors.Text
    $script:notifyToggle.ToolTipText = "Toggle themed toast popups; tray hover/status text still updates"
    Set-TrayCommandItemVisualState -Item $script:notifyToggle -ChipText "TOAST"
    $script:notifyToggle.Add_Click({
        $script:EnableBalloonNotifications = -not $script:EnableBalloonNotifications
        $script:TrayConfig.notificationsEnabled = $script:EnableBalloonNotifications
        $script:notifyToggle.Checked = $script:EnableBalloonNotifications
        $state = if ($script:EnableBalloonNotifications) { "enabled" } else { "disabled" }
        Save-TrayConfig $script:TrayConfig
        Write-TrayLog "Toast popups $state"
        Set-TrayLastAction -Message "Toast popups $state"
        Update-MenuState
    })
    $settingsMenu.DropDownItems.Add($script:notifyToggle) | Out-Null

    # Sound toggle
    $soundToggle = New-Object System.Windows.Forms.ToolStripMenuItem
    $soundToggle.Text = "Tray Audio Cues"
    $soundToggle.Checked = $script:TrayConfig.soundEnabled
    $soundToggle.BackColor = $script:Colors.Background
    $soundToggle.ForeColor = $script:Colors.Text
    $soundToggle.Font = $script:FontMenuRow
    $soundToggle.Image = New-ActionBitmap -Action "Sound" -Color $script:Colors.Text
    $soundToggle.ToolTipText = "Toggle tray audio cues; toasts and status text still update"
    Set-TrayCommandItemVisualState -Item $soundToggle -ChipText "AUDIO"
    $soundToggle.Add_Click({
        $script:TrayConfig.soundEnabled = -not $script:TrayConfig.soundEnabled
        $soundToggle.Checked = $script:TrayConfig.soundEnabled
        Save-TrayConfig $script:TrayConfig
        Write-TrayLog "Tray audio cues: $($script:TrayConfig.soundEnabled)"
        $state = if ($script:TrayConfig.soundEnabled) { "enabled" } else { "disabled" }
        Set-TrayLastAction -Message "Tray audio cues $state"
        Update-MenuState
    })
    $settingsMenu.DropDownItems.Add($soundToggle) | Out-Null

    $settingsMenu.DropDownItems.Add((New-Object System.Windows.Forms.ToolStripSeparator)) | Out-Null

    # Open Settings Panel
    $settingsPanelItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $settingsPanelItem.Text = "Open Settings..."
    $settingsPanelItem.BackColor = $script:Colors.Background
    $settingsPanelItem.ForeColor = $script:Colors.Text
    $settingsPanelItem.Font = $script:FontMenuRow
    $settingsPanelItem.Image = New-ActionBitmap -Action "Settings" -Color $script:Colors.Text
    Set-TrayCommandItemVisualState -Item $settingsPanelItem -ChipText "CONFIG"
    $settingsPanelItem.Add_Click({
        Show-SettingsPanel -Config $script:TrayConfig -OnSave {
            param($cfg)
            $script:TrayConfig = $cfg
            $script:EnableBalloonNotifications = [bool]$script:TrayConfig.notificationsEnabled
            Write-TrayLog "Settings saved"
            Set-TrayLastAction -Message "Tray settings saved"
            Update-MenuState
        }
    })
    $settingsMenu.DropDownItems.Add($settingsPanelItem) | Out-Null

    # View Log
    $logItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $logItem.Text = "View Tray Log File"
    $logItem.BackColor = $script:Colors.Background
    $logItem.ForeColor = $script:Colors.TextDim
    $logItem.Font = $script:FontMenuRow
    $logItem.Image = New-ActionBitmap -Action "Log" -Color $script:Colors.TextDim
    $logItem.ToolTipText = "Opens current tray log: $script:LogFile"
    Set-TrayCommandItemVisualState -Item $logItem -ChipText "LOG"
    $logItem.Add_Click({ Open-LogFile })
    $settingsMenu.DropDownItems.Add($logItem) | Out-Null

    # Open Tray Settings Folder
    $configFolderItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $configFolderItem.Text = "Open Tray Settings Folder"
    $configFolderItem.BackColor = $script:Colors.Background
    $configFolderItem.ForeColor = $script:Colors.TextDim
    $configFolderItem.Font = $script:FontMenuRow
    $configFolderItem.Image = New-ActionBitmap -Action "Folder" -Color $script:Colors.TextDim
    $configFolderItem.ToolTipText = "Opens tray-config.json storage: $(Get-TrayConfigDir)"
    Set-TrayCommandItemVisualState -Item $configFolderItem -ChipText "FOLDER"
    $configFolderItem.Add_Click({ Open-ConfigFolder })
    $settingsMenu.DropDownItems.Add($configFolderItem) | Out-Null

    # Open Installed Runtime Folder
    $runtimeFolderItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $runtimeFolderItem.Text = "Open Installed Runtime Folder"
    $runtimeFolderItem.BackColor = $script:Colors.Background
    $runtimeFolderItem.ForeColor = $script:Colors.TextDim
    $runtimeFolderItem.Font = $script:FontMenuRow
    $runtimeFolderItem.Image = New-ActionBitmap -Action "Folder" -Color $script:Colors.TextDim
    $runtimeFolderItem.ToolTipText = "Opens abso.yaml, installed binaries, backups, and deployed tray assets"
    Set-TrayCommandItemVisualState -Item $runtimeFolderItem -ChipText "RUNTIME"
    $runtimeFolderItem.Add_Click({ Open-RuntimeFolder })
    $settingsMenu.DropDownItems.Add($runtimeFolderItem) | Out-Null

    $menu.Items.Add($settingsMenu) | Out-Null

    # ─── STATUS BAR ───

    $menu.Items.Add((New-Object System.Windows.Forms.ToolStripSeparator)) | Out-Null

    $script:statusBarItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $script:statusBarItem.Text = "  Ready"
    $script:statusBarItem.AccessibleName = "__status_bar__"
    $script:statusBarItem.AccessibleDescription = "READY"
    $script:statusBarItem.Enabled = $false
    $script:statusBarItem.BackColor = $script:Colors.BackgroundDark
    $script:statusBarItem.ForeColor = [System.Drawing.Color]::FromArgb(255, 95, 127, 127)
    $script:statusBarItem.Font = $script:FontMono
    $script:statusBarItem.Image = New-ActionBitmap -Action "Info" -Color $script:statusBarItem.ForeColor
    $menu.Items.Add($script:statusBarItem) | Out-Null

    # ─── EXIT SECTION ───

    $menu.Items.Add((New-Object System.Windows.Forms.ToolStripSeparator)) | Out-Null

    # Restart
    $restartItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $restartItem.Text = "Restart Tray"
    $restartItem.BackColor = $script:Colors.Background
    $restartItem.ForeColor = $script:Colors.TextDim
    $restartItem.Font = $script:FontMenuRow
    $restartItem.Image = New-ActionBitmap -Action "Refresh" -Color $script:Colors.TextDim
    $restartItem.Add_Click({
        $restartToken = [guid]::NewGuid().ToString("N")
        try {
            Set-RestartSuccessSoundMarker -RestartToken $restartToken
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
            $restartArgs = @(
                "-NoProfile",
                "-ExecutionPolicy", "Bypass",
                "-WindowStyle", "Hidden",
                "-File", "`"$PSCommandPath`"",
                "-Hidden",
                "-RestartToken", "`"$restartToken`""
            )
            Start-Process powershell.exe -ArgumentList ($restartArgs -join " ") -WindowStyle Hidden -ErrorAction Stop | Out-Null
            [System.Windows.Forms.Application]::Exit()
        }
        catch {
            Clear-RestartSuccessSoundMarker
            if ($script:notifyIcon) { $script:notifyIcon.Visible = $true }
            Set-TrayLastAction -Message "Tray restart failed: $($_.Exception.Message)"
            Restore-TrayTooltipFromState -Force
            Update-MenuState
            Show-Notification -Title "computa" -Message "Tray restart failed: $($_.Exception.Message)" -Type "Error" -ActionName "Refresh" -ActionColor $script:Colors.AccentAmber
        }
    })
    $menu.Items.Add($restartItem) | Out-Null

    # About
    $aboutItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $aboutItem.Text = "About computa"
    $aboutItem.BackColor = $script:Colors.Background
    $aboutItem.ForeColor = $script:Colors.TextDim
    $aboutItem.Font = $script:FontMenuRow
    $aboutItem.Image = New-ActionBitmap -Action "Info" -Color $script:Colors.TextDim
    $aboutItem.Add_Click({ Show-AboutPanel })
    $menu.Items.Add($aboutItem) | Out-Null

    # Exit
    $exitItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $exitItem.Text = "Exit"
    $exitItem.BackColor = $script:Colors.Background
    $exitItem.ForeColor = $script:Colors.TextDim
    $exitItem.Font = $script:FontMenuRow
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
    Start-TrayMenuPulseTimer

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
        if ($script:TrayConfig.favorites.Count -le 0) {
            Show-Notification -Title "computa" -Message "No favorite profile configured for double-click." -Type "Info" -ActionName "Favorite" -ActionColor $script:Colors.AccentAmber
            Set-TrayLastAction -Message "Double-click ignored: no favorite"
            Update-MenuState
            return
        }

        $lastFav = "$($script:TrayConfig.favorites[0])"
        if ($script:Profiles.Contains($lastFav)) {
            Apply-Profile $lastFav
        }
        else {
            $favName = Get-TrayProfileDisplayName -ProfileId $lastFav
            $favMissingVisual = Get-TrayProfileToastVisualArgs -ProfileId $lastFav -Profile $null
            Show-Notification @favMissingVisual -Title $favName -Message "Favorite profile is not in the current profile list." -Type "Warning" -MetaText $lastFav
            Set-TrayLastAction -Message "Favorite missing: $favName"
            Update-MenuState
        }
    })

    # ─── DEFAULT PROFILE (notify only, do not auto-apply) ───

    if (-not $script:activeProfile -and $script:TrayConfig.defaultProfile) {
        $defaultProfileId = "$($script:TrayConfig.defaultProfile)"
        if ($script:Profiles.Contains($defaultProfileId)) {
            $defProfile = $script:Profiles[$defaultProfileId]
            Write-TrayLog "Default profile available: $defaultProfileId (not auto-applying)"
            $defaultReminderVisual = Get-TrayProfileToastVisualArgs -ProfileId $defaultProfileId -Profile $defProfile
            $defaultReminderTitle = Get-TrayProfileObjectDisplayName -Profile $defProfile -Fallback $defaultProfileId
            Show-Notification @defaultReminderVisual -Title $defaultReminderTitle -Message "Default profile ready. Open tray menu to apply." -Type "Info" -MetaText $defaultProfileId
            Set-TrayLastAction -Message "Startup reminder: $defaultReminderTitle"
            Update-MenuState
        }
        else {
            $defaultProfileName = Get-TrayProfileDisplayName -ProfileId $defaultProfileId
            Write-TrayLog "Default startup reminder profile '$defaultProfileId' is not in the current profile list" -Level "WARN"
            $defaultMissingVisual = Get-TrayProfileToastVisualArgs -ProfileId $defaultProfileId -Profile $null
            Show-Notification @defaultMissingVisual -Title $defaultProfileName -Message "Startup reminder profile is not in the current profile list." -Type "Warning" -MetaText $defaultProfileId
            Set-TrayLastAction -Message "Startup reminder missing: $defaultProfileName"
            Update-MenuState
        }
    }

    # ─── SHOW QUICK PANEL IF ENABLED ───

    if ($script:TrayConfig.showQuickPanel) {
        $startupQuickPanelEmpty = Get-QuickPanelEmptyStatus
        $startupQuickPanelPendingApplyText = Get-ActiveProfilePendingApplyText
        $startupQuickPanelWindowsRestartText = Get-ActiveProfileRebootPendingText
        $startupQuickPanelVerificationText = Get-ActiveProfileVerificationInProgressText
        Show-QuickPanel -Favorites $script:TrayConfig.favorites -Profiles $script:Profiles -ActiveProfile $script:activeProfile -ActivePendingApplyText $startupQuickPanelPendingApplyText -ActiveWindowsRestartText $startupQuickPanelWindowsRestartText -ActiveVerificationText $startupQuickPanelVerificationText -EmptyMessage $startupQuickPanelEmpty.Message -EmptyProfileId $startupQuickPanelEmpty.ProfileId -OnApply { param($id) Apply-Profile $id }
        $script:TrayConfig.showQuickPanel = [bool]$script:QuickPanelVisible
    }

    # Only play restart sound once the new tray instance has fully initialized.
    Invoke-RestartSuccessSoundIfPending

    # ─── PROCESS GUARD (demote Discord etc. from RealTime) ───
    Start-ProcessGuardTimer

    # ─── LAUNCH SANITIZER (kill overlays/capture/sync while game is alive) ───
    Start-LaunchSanitizerTimer

    # Do not run full profile verification automatically on tray startup.
    # Even though ``state --json --verify`` is read-only, it still exercises
    # display/NVIDIA/readback paths and has correlated with black compositor
    # blinks on mixed-refresh VRR systems. Startup only restores remembered
    # state; explicit same-profile clicks, apply, and pending-fix actions still
    # run verification before deciding whether to write anything.
    if (-not [string]::IsNullOrWhiteSpace([string]$script:activeProfile)) {
        Write-TrayLog "Startup profile verification deferred; active profile restored from remembered state only"
    }

    # Narrow one-shot command file used by local automation to ask the already
    # elevated tray to run vetted tray actions. Currently only supports the
    # targeted apply-pending path; it cannot run arbitrary commands.
    Invoke-TrayCommandFile

    # Cold-start complete. Log time-to-ready so regressions surface in the
    # tray log on every relaunch. Target: well under 2000ms now that the
    # catalog load is cache-first.
    if ($script:ColdStartStopwatch) {
        $script:ColdStartStopwatch.Stop()
        Write-TrayLog "ABSO Tray ready in $($script:ColdStartStopwatch.ElapsedMilliseconds)ms (cold-start wall clock)" -Level "INFO"
    }

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
        Write-TrayLog "Fatal location: $(($_.InvocationInfo.PositionMessage -replace '\r?\n',' '))" -Level "ERROR"
        Write-TrayLog "Fatal stack: $(($_.ScriptStackTrace -replace '\r?\n',' <- '))" -Level "ERROR"
    } catch {}
    try {
        [System.Windows.Forms.MessageBox]::Show(
            "computa Tray encountered a fatal error and exited.`n`n$fatal`n`nSee log: $($script:LogFile)",
            "computa",
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Error
        ) | Out-Null
    }
    catch {}
}
finally {
    # Reap any pending background catalog refresh timer.
    if ($script:BackgroundCatalogTimer) {
        try { $script:BackgroundCatalogTimer.Stop(); $script:BackgroundCatalogTimer.Dispose() } catch {}
        $script:BackgroundCatalogTimer = $null
    }
    Stop-LaunchSanitizerTimer
    Stop-ProcessGuardTimer
    Stop-AuditRuntime -KillProcess
    Stop-NotificationTooltipRestoreTimer
    Stop-TrayMenuPulseTimer
    if ($script:StartupIconHealTimer) {
        try { $script:StartupIconHealTimer.Stop() } catch {}
        try { $script:StartupIconHealTimer.Dispose() } catch {}
    }
    if ($script:ApplyAnimTimer) {
        $script:ApplyAnimTimer.Stop()
        $script:ApplyAnimTimer.Dispose()
    }
    Stop-ActiveProfileVerificationRuntime -KillProcess
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
        $script:FontNormal = $null
    }
    if ($script:FontBold) {
        try { $script:FontBold.Dispose() } catch {}
        $script:FontBold = $null
    }
    # Phosphor type-system fonts (added during the Tron HUD overhaul) -
    # previously leaked on exit because the finally block only knew about
    # the legacy FontNormal / FontBold pair.
    foreach ($fontVar in @('FontEyebrow','FontHero','FontMono','FontMenuRow','FontMenuRowBold','FontSectionHeader','FontCategoryHeader')) {
        $fontObj = Get-Variable -Scope Script -Name $fontVar -ValueOnly -ErrorAction SilentlyContinue
        if ($fontObj) {
            try { $fontObj.Dispose() } catch {}
            Set-Variable -Scope Script -Name $fontVar -Value $null
        }
    }
    if ($script:mutex) {
        try { $script:mutex.ReleaseMutex() } catch {}
        $script:mutex.Close()
        $script:mutex = $null
    }
}
