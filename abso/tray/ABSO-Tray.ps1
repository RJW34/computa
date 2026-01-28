# ABSO-Tray.ps1 - System tray for A.B.S.O. with Dark Theme
# Memory: ~25-30MB | CPU: Near-zero when idle
# Left-click shows profile menu, applies via CLI, monitors game lifecycle

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

# ============================================================================
# SOUND EFFECT
# ============================================================================

$script:SoundFile = Join-Path $PSScriptRoot "pokemon-red_blue_yellow-save-game-sound-effect.mp3"
$script:FailSoundFile = Join-Path $PSScriptRoot "hit-weak-not-very-effective.mp3"

# Reusable MediaPlayer instance to avoid memory leaks from creating new instances
$script:MediaPlayer = $null

function Get-MediaPlayer {
    <#
    .SYNOPSIS
    Gets or creates a reusable MediaPlayer instance.
    #>
    if ($null -eq $script:MediaPlayer) {
        $script:MediaPlayer = New-Object System.Windows.Media.MediaPlayer

        # Register MediaEnded event to close the media and free resources
        Register-ObjectEvent -InputObject $script:MediaPlayer -EventName MediaEnded -Action {
            $script:MediaPlayer.Close()
        } | Out-Null
    }
    return $script:MediaPlayer
}

function Play-SuccessSound {
    <#
    .SYNOPSIS
    Plays the success sound effect at 20% volume when a profile is applied.
    #>
    try {
        if (Test-Path $script:SoundFile) {
            $player = Get-MediaPlayer
            $player.Close()  # Close any previous media
            $player.Open([Uri]$script:SoundFile)
            $player.Volume = 0.20  # 20% volume
            $player.Play()
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
    <#
    .SYNOPSIS
    Plays the fail sound effect at 100% volume when a profile apply fails.
    #>
    try {
        if (Test-Path $script:FailSoundFile) {
            $player = Get-MediaPlayer
            $player.Close()  # Close any previous media
            $player.Open([Uri]$script:FailSoundFile)
            $player.Volume = 1.0  # 100% volume
            $player.Play()
            Write-TrayLog "Playing fail sound"
        }
        else {
            Write-TrayLog "Fail sound file not found: $($script:FailSoundFile)" -Level "WARN"
        }
    }
    catch {
        Write-TrayLog "Failed to play fail sound: $($_.Exception.Message)" -Level "WARN"
    }
}

function Test-SoundFilesExist {
    <#
    .SYNOPSIS
    Validates that sound effect files exist at startup and logs warnings if missing.
    Returns true if all files exist, false otherwise.
    #>
    $allPresent = $true

    if (-not (Test-Path $script:SoundFile)) {
        Write-TrayLog "SUCCESS SOUND FILE MISSING: $($script:SoundFile)" -Level "WARN"
        Write-TrayLog "Profile apply will still work, but no success sound will play." -Level "WARN"
        $allPresent = $false
    }

    if (-not (Test-Path $script:FailSoundFile)) {
        Write-TrayLog "FAIL SOUND FILE MISSING: $($script:FailSoundFile)" -Level "WARN"
        Write-TrayLog "Profile apply will still work, but no fail sound will play." -Level "WARN"
        $allPresent = $false
    }

    if ($allPresent) {
        Write-TrayLog "Sound files validated successfully"
    }

    return $allPresent
}

# ============================================================================
# DARK THEME COLORS
# ============================================================================

$script:Colors = @{
    Background   = [System.Drawing.Color]::FromArgb(255, 32, 32, 32)
    Hover        = [System.Drawing.Color]::FromArgb(255, 55, 55, 58)
    Text         = [System.Drawing.Color]::FromArgb(255, 220, 220, 220)
    TextDim      = [System.Drawing.Color]::FromArgb(255, 140, 140, 140)
    TextDisabled = [System.Drawing.Color]::FromArgb(255, 90, 90, 90)
    Border       = [System.Drawing.Color]::FromArgb(255, 60, 60, 60)
    Separator    = [System.Drawing.Color]::FromArgb(255, 55, 55, 55)
    AccentGold   = [System.Drawing.Color]::FromArgb(255, 220, 180, 70)
    AccentGreen  = [System.Drawing.Color]::FromArgb(255, 90, 200, 120)
    CatFighting  = [System.Drawing.Color]::FromArgb(255, 230, 120, 120)
    CatARPG      = [System.Drawing.Color]::FromArgb(255, 180, 150, 220)
    CatShooter   = [System.Drawing.Color]::FromArgb(255, 120, 180, 220)
    CatOther     = [System.Drawing.Color]::FromArgb(255, 150, 200, 150)
    CatProd      = [System.Drawing.Color]::FromArgb(255, 220, 190, 120)
}

# ============================================================================
# LOGGING
# ============================================================================

$script:LogFile = Join-Path $env:TEMP "abso_tray.log"

function Write-TrayLog {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$timestamp] [$Level] $Message"
    try {
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

    $maxLen = [Math]::Min(63, "$Title - $Message".Length)
    $script:notifyIcon.Text = "$Title - $Message".Substring(0, $maxLen)

    if ($script:EnableBalloonNotifications) {
        $icon = switch ($Type) {
            "Warning" { [System.Windows.Forms.ToolTipIcon]::Warning }
            "Error" { [System.Windows.Forms.ToolTipIcon]::Error }
            default { [System.Windows.Forms.ToolTipIcon]::Info }
        }
        $script:notifyIcon.ShowBalloonTip(3000, $Title, $Message, $icon)
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

$script:ScriptDir = $PSScriptRoot
$script:ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$script:WatcherPIDFile = Join-Path $env:TEMP "abso_watcher.pid"
$script:ActiveProfileFile = Join-Path $env:TEMP "abso_active_profile.json"

# ============================================================================
# PROFILE DEFINITIONS
# ============================================================================

$script:AppVersion = "1.2.0"

$script:Profiles = [ordered]@{
    # --- Productivity ---
    "productivity" = @{
        Name     = "Desktop / Productivity"
        Sub      = "HDR + VRR + Balanced"
        Cat      = "Productivity"
        Desc     = "Browsing, coding, general desktop. VRR on, HDR enabled."
        Exes     = @("Code.exe", "devenv.exe", "chrome.exe", "firefox.exe", "msedge.exe")
    }

    # --- Fighting Games: Rivals 2 ---
    "rivals2-offline"   = @{
        Name     = "Rivals 2: Training"
        Sub      = "LLM Ultra | Uncapped"
        Cat      = "Fighting"
        Desc     = "Training/combos. LLM Ultra, no sync, max refresh."
        Exes     = @("Rivals2-Win64-Shipping.exe", "RivalsofAether2.exe", "Rivals2.exe")
    }
    "rivals2-online"    = @{
        Name     = "Rivals 2: Online"
        Sub      = "LLM ON | 240fps | Rollback-Safe"
        Cat      = "Fighting"
        Desc     = "Ranked/online. LLM ON (not Ultra), 240fps cap, 240Hz."
        Exes     = @("Rivals2-Win64-Shipping.exe", "RivalsofAether2.exe", "Rivals2.exe")
    }
    "rivals2-tournament-sim-144hz" = @{
        Name     = "Rivals 2: Tournament Sim"
        Sub      = "LLM ON | 144Hz | Practice Transfer"
        Cat      = "Fighting"
        Desc     = "Simulates tournament PCs (144Hz). Practice transfer focus."
        Exes     = @("Rivals2-Win64-Shipping.exe", "RivalsofAether2.exe", "Rivals2.exe")
    }
    "rivals2-300hz-max" = @{
        Name     = "Rivals 2: 300Hz MAX"
        Sub      = "LLM Ultra | 300Hz | No Compromises"
        Cat      = "Fighting"
        Desc     = "Maximum performance. 300Hz, LLM Ultra, Ultimate Performance."
        Exes     = @("Rivals2-Win64-Shipping.exe", "RivalsofAether2.exe", "Rivals2.exe")
    }

    # --- Fighting Games: Melee ---
    "slippi-melee"      = @{
        Name     = "Slippi Melee"
        Sub      = "LLM Ultra | DX12 + HAGS"
        Cat      = "Fighting"
        Desc     = "Competitive Melee. LLM Ultra, no sync, max refresh."
        Exes     = @("Slippi Dolphin.exe", "Dolphin.exe")
    }

    # --- Fighting Games: SSBU ---
    "ryujinx-ssbu"      = @{
        Name     = "SSBU (Ryujinx)"
        Sub      = "LLM Ultra | Vulkan"
        Cat      = "Fighting"
        Desc     = "Smash Ultimate via Ryujinx. Fixed 60fps, latency-first."
        Exes     = @("Ryujinx.exe", "Ryujinx.Ava.exe", "Ryujinx.Headless.SDL2.exe")
    }

    # --- ARPG ---
    "diablo4"           = @{
        Name     = "Diablo 4"
        Sub      = "HDR + Reflex | Balanced"
        Cat      = "ARPG"
        Desc     = "Native HDR + Reflex. Balanced for variable FPS."
        Exes     = @("Diablo IV.exe")
    }

    # --- Shooter ---
    "cod-bo7"           = @{
        Name     = "CoD: Black Ops 7"
        Sub      = "HDR + Reflex | Low Latency"
        Cat      = "Shooter"
        Desc     = "Native HDR + Reflex. Competitive FPS settings."
        Exes     = @("cod.exe", "BlackOps7.exe")
    }
}

$script:CategoryOrder = @("Productivity", "Fighting", "ARPG", "Shooter", "Other")
$script:CategoryColors = @{
    "Productivity" = $script:Colors.CatProd
    "Fighting"     = $script:Colors.CatFighting
    "ARPG"         = $script:Colors.CatARPG
    "Shooter"      = $script:Colors.CatShooter
    "Other"        = $script:Colors.CatOther
}

# ============================================================================
# ICON
# ============================================================================

# Icon file paths
$script:IconInactive = Join-Path $script:ScriptDir "favicon.ico"
$script:IconActive = Join-Path $script:ScriptDir "260 Swampert.ico"

function New-ABSOIcon {
    param([switch]$Active)

    $iconPath = if ($Active) { $script:IconActive } else { $script:IconInactive }

    if (Test-Path $iconPath) {
        try {
            # Load as image (works for PNG files) and convert to icon
            $img = [System.Drawing.Image]::FromFile($iconPath)
            $bmp = New-Object System.Drawing.Bitmap($img, 16, 16)
            $hIcon = $bmp.GetHicon()
            $icon = [System.Drawing.Icon]::FromHandle($hIcon)
            $img.Dispose()
            $bmp.Dispose()
            return $icon
        }
        catch {
            Write-TrayLog "Failed to load icon from $iconPath : $($_.Exception.Message)" -Level "WARN"
        }
    }

    # Fallback: draw simple icon if file not found or load failed
    $bmp = New-Object System.Drawing.Bitmap(16, 16)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $g.Clear([System.Drawing.Color]::Transparent)

    $color = if ($Active) { $script:Colors.AccentGreen } else { $script:Colors.AccentGold }
    $brush = New-Object System.Drawing.SolidBrush($color)
    $g.FillEllipse($brush, 2, 2, 12, 12)

    $g.Dispose()
    $brush.Dispose()

    $hIcon = $bmp.GetHicon()
    $icon = [System.Drawing.Icon]::FromHandle($hIcon)
    $bmp.Dispose()
    return $icon
}

# ============================================================================
# WATCHER
# ============================================================================

function Stop-ExistingWatcher {
    if (Test-Path $script:WatcherPIDFile) {
        try {
            $watcherPid = [int](Get-Content $script:WatcherPIDFile -ErrorAction SilentlyContinue)
            if ($watcherPid -gt 0) {
                Write-TrayLog "Stopping existing watcher PID: $watcherPid"
                Stop-Process -Id $watcherPid -Force -ErrorAction SilentlyContinue
            }
        }
        catch {
            Write-TrayLog "Failed to stop watcher: $($_.Exception.Message)" -Level "WARN"
        }
        Remove-Item $script:WatcherPIDFile -Force -ErrorAction SilentlyContinue
    }
}

function Start-GameWatcher {
    param([string]$ProfileId, [string[]]$Executables)

    Stop-ExistingWatcher

    $exeList = $Executables -join ','
    $watcherPath = Join-Path $script:ScriptDir "ABSO-Watcher.ps1"
    $trayPath = Join-Path $script:ScriptDir "ABSO-Tray.ps1"

    $proc = Start-Process powershell -ArgumentList @(
        "-NoProfile", "-WindowStyle", "Hidden", "-ExecutionPolicy", "Bypass",
        "-File", "`"$watcherPath`"",
        "-ExeList", "`"$exeList`"",
        "-TrayPID", $PID,
        "-TrayScript", "`"$trayPath`""
    ) -WindowStyle Hidden -PassThru

    $proc.Id | Out-File $script:WatcherPIDFile -Force

    @{ ProfileId = $ProfileId; Executables = $Executables } |
    ConvertTo-Json | Out-File $script:ActiveProfileFile -Force
}

# ============================================================================
# APPLY / RESTORE
# ============================================================================

function Apply-Profile {
    param([string]$ProfileId)

    Write-TrayLog "Apply-Profile called with: $ProfileId"
    $profile = $script:Profiles[$ProfileId]

    # Validate profile exists
    if (-not $profile) {
        Write-TrayLog "Profile not found: $ProfileId" -Level "ERROR"
        Play-FailSound
        Show-Notification -Title "A.B.S.O." -Message "Profile not found: $ProfileId" -Type "Error"
        return
    }

    # Show inactive icon while applying
    $script:notifyIcon.Icon = New-ABSOIcon
    $script:notifyIcon.Text = "A.B.S.O. - Applying..."

    try {
        $tempFile = [System.IO.Path]::GetTempFileName()
        $errFile = "$tempFile.err"

        Write-TrayLog "Running: python -m abso apply $ProfileId --json"
        Start-Process -FilePath "python" -ArgumentList "-m", "abso", "apply", $ProfileId, "--json" `
            -NoNewWindow -Wait -WorkingDirectory $script:ProjectRoot `
            -RedirectStandardOutput $tempFile -RedirectStandardError $errFile

        $rawOutput = Get-Content $tempFile -Raw -ErrorAction SilentlyContinue
        $errOutput = Get-Content $errFile -Raw -ErrorAction SilentlyContinue
        Remove-Item $tempFile -Force -ErrorAction SilentlyContinue
        Remove-Item $errFile -Force -ErrorAction SilentlyContinue

        Write-TrayLog "CLI output: $rawOutput"
        if ($errOutput) { Write-TrayLog "CLI stderr: $errOutput" -Level "WARN" }

        if (-not $rawOutput) { throw "No output from CLI" }

        $json = $rawOutput | ConvertFrom-Json

        if ($json.success -and $json.data.success) {
            $msg = "$($profile.Name) ($($profile.Sub))"
            if ($json.data.requires_reboot) { $msg += " - Restart required" }

            Write-TrayLog "Profile applied successfully: $ProfileId"
            Play-SuccessSound
            Show-Notification -Title "A.B.S.O." -Message $msg -Type "Info"
            Start-GameWatcher -ProfileId $ProfileId -Executables $profile.Exes

            $script:activeProfile = $ProfileId
            Update-MenuState
        }
        else {
            $err = if ($json.error) { $json.error } else { "Unknown error" }
            Write-TrayLog "Profile apply failed: $err" -Level "ERROR"
            Play-FailSound
            Show-Notification -Title "A.B.S.O." -Message "Failed: $err" -Type "Error"
            Update-MenuState  # Restore icon state
        }
    }
    catch {
        Write-TrayLog "Apply-Profile exception: $($_.Exception.Message)" -Level "ERROR"
        Play-FailSound
        Show-Notification -Title "A.B.S.O." -Message "Error: $($_.Exception.Message)" -Type "Error"
        Update-MenuState  # Restore icon state
    }
}

function Restore-Settings {
    # Show inactive icon while restoring
    $script:notifyIcon.Icon = New-ABSOIcon
    $script:notifyIcon.Text = "A.B.S.O. - Restoring..."

    try {
        $tempFile = [System.IO.Path]::GetTempFileName()
        $errFile = "$tempFile.err"

        Start-Process -FilePath "python" -ArgumentList "-m", "abso", "restore", "latest", "--json" `
            -NoNewWindow -Wait -WorkingDirectory $script:ProjectRoot `
            -RedirectStandardOutput $tempFile -RedirectStandardError $errFile

        $rawOutput = Get-Content $tempFile -Raw -ErrorAction SilentlyContinue
        Remove-Item $tempFile -Force -ErrorAction SilentlyContinue
        Remove-Item $errFile -Force -ErrorAction SilentlyContinue

        if (-not $rawOutput) { throw "No output" }

        $json = $rawOutput | ConvertFrom-Json

        if ($json.success) {
            Show-Notification -Title "A.B.S.O." -Message "Settings restored" -Type "Info"
            Stop-ExistingWatcher
            $script:activeProfile = $null
            Update-MenuState
        }
        else {
            Show-Notification -Title "A.B.S.O." -Message "Failed: $($json.error)" -Type "Warning"
        }
    }
    catch {
        Show-Notification -Title "A.B.S.O." -Message "Error: $($_.Exception.Message)" -Type "Warning"
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

        # Update text with visual indicator
        $p = $script:Profiles[$item.Tag]
        if ($isActive) {
            $item.Text = "  >>  $($p.Name)"
            $item.ForeColor = $script:Colors.AccentGreen
            $item.Font = New-Object System.Drawing.Font("Segoe UI", 9, [System.Drawing.FontStyle]::Bold)
        }
        else {
            $item.Text = "      $($p.Name)"
            $item.ForeColor = $script:Colors.Text
            $item.Font = New-Object System.Drawing.Font("Segoe UI", 9)
        }
    }
    $script:restoreItem.Enabled = ($null -ne $script:activeProfile)

    if ($script:activeProfile) {
        $p = $script:Profiles[$script:activeProfile]
        $script:notifyIcon.Icon = New-ABSOIcon -Active
        # Truncate for tooltip limit
        $tooltipText = "A.B.S.O. - $($p.Name)"
        if ($tooltipText.Length -gt 63) {
            $tooltipText = $tooltipText.Substring(0, 60) + "..."
        }
        $script:notifyIcon.Text = $tooltipText

        # Update status in menu
        if ($script:statusItem) {
            $script:statusItem.Text = "      Active: $($p.Name)"
            $script:statusItem.ForeColor = $script:Colors.AccentGreen
        }
    }
    else {
        $script:notifyIcon.Icon = New-ABSOIcon
        $script:notifyIcon.Text = "A.B.S.O. - Ready"

        if ($script:statusItem) {
            $script:statusItem.Text = "      Status: Ready"
            $script:statusItem.ForeColor = $script:Colors.AccentGreen
        }
    }
}

# ============================================================================
# OWNER-DRAW HANDLER
# ============================================================================

function Handle-DrawItem {
    param($sender, $e)

    $item = $sender
    $g = $e.Graphics
    $bounds = $e.Bounds

    # Background
    $bgColor = $script:Colors.Background
    if (($e.State -band [System.Windows.Forms.DrawItemState]::Selected) -ne 0) {
        $bgColor = $script:Colors.Hover
    }

    $bgBrush = New-Object System.Drawing.SolidBrush($bgColor)
    $g.FillRectangle($bgBrush, $bounds)
    $bgBrush.Dispose()

    # Left accent on hover
    if (($e.State -band [System.Windows.Forms.DrawItemState]::Selected) -ne 0 -and $item.Enabled) {
        $accentBrush = New-Object System.Drawing.SolidBrush($script:Colors.AccentGreen)
        $g.FillRectangle($accentBrush, $bounds.X, $bounds.Y + 2, 3, $bounds.Height - 4)
        $accentBrush.Dispose()
    }

    # Text
    $textColor = $script:Colors.Text
    if (-not $item.Enabled) {
        $textColor = $script:Colors.TextDisabled
    }
    elseif ($item.Tag -eq "dim") {
        $textColor = $script:Colors.TextDim
    }
    elseif ($item.Tag -eq "header") {
        $textColor = $script:Colors.AccentGold
    }
    elseif ($item.Tag -like "cat:*") {
        $catName = $item.Tag.Substring(4)
        if ($script:CategoryColors.ContainsKey($catName)) {
            $textColor = $script:CategoryColors[$catName]
        }
    }

    $textBrush = New-Object System.Drawing.SolidBrush($textColor)
    $textRect = New-Object System.Drawing.RectangleF($bounds.X + 24, $bounds.Y, $bounds.Width - 24, $bounds.Height)
    $sf = New-Object System.Drawing.StringFormat
    $sf.LineAlignment = [System.Drawing.StringAlignment]::Center

    $font = $item.Font
    $createdFont = $false
    if ($item.Tag -eq "header") {
        $font = New-Object System.Drawing.Font($item.Font.FontFamily, 10, [System.Drawing.FontStyle]::Bold)
        $createdFont = $true
    }
    elseif ($item.Tag -like "cat:*") {
        $font = New-Object System.Drawing.Font($item.Font.FontFamily, 8.5, [System.Drawing.FontStyle]::Bold)
        $createdFont = $true
    }

    $g.DrawString($item.Text, $font, $textBrush, $textRect, $sf)

    $textBrush.Dispose()
    $sf.Dispose()
    if ($createdFont) { $font.Dispose() }

    # Checkmark
    if ($item.Checked) {
        $checkBrush = New-Object System.Drawing.SolidBrush($script:Colors.AccentGreen)
        $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
        $cx = $bounds.X + 12
        $cy = $bounds.Y + ($bounds.Height / 2)
        $g.FillEllipse($checkBrush, $cx - 5, $cy - 5, 10, 10)
        $checkBrush.Dispose()

        $checkPen = New-Object System.Drawing.Pen($script:Colors.Background, 1.5)
        $g.DrawLine($checkPen, $cx - 2, $cy, $cx, $cy + 2)
        $g.DrawLine($checkPen, $cx, $cy + 2, $cx + 3, $cy - 2)
        $checkPen.Dispose()
    }
}

function Handle-MeasureItem {
    param($sender, $e)
    $e.ItemHeight = 26
    $e.ItemWidth = 280
}

# ============================================================================
# SYSTEM INFO
# ============================================================================

function Get-SystemInfo {
    <#
    .SYNOPSIS
    Gets basic system info for display in the tray menu.
    #>
    $info = @{
        GPU = "Unknown GPU"
        Monitor = "Unknown"
        RefreshRate = "?"
    }

    try {
        # GPU - filter out virtual display adapters
        $virtualAdapters = @(
            "Parsec",
            "Virtual",
            "Microsoft Basic",
            "Microsoft Remote",
            "VNC",
            "TeamViewer",
            "AnyDesk",
            "Citrix",
            "VMware",
            "VirtualBox",
            "Hyper-V"
        )

        $gpus = Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue
        $realGpu = $gpus | Where-Object {
            $name = $_.Name
            $isVirtual = $false
            foreach ($v in $virtualAdapters) {
                if ($name -like "*$v*") {
                    $isVirtual = $true
                    break
                }
            }
            -not $isVirtual
        } | Select-Object -First 1

        # Fallback to first GPU if no real GPU found
        if (-not $realGpu) {
            $realGpu = $gpus | Select-Object -First 1
        }

        if ($realGpu) {
            $gpuName = $realGpu.Name -replace "NVIDIA ", "" -replace "GeForce ", "" -replace "AMD ", "" -replace "Radeon ", ""
            $info.GPU = $gpuName.Trim()
        }

        # Monitor - try to get from registry or WMI
        $monitor = Get-CimInstance WmiMonitorID -Namespace root/wmi -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($monitor -and $monitor.UserFriendlyName) {
            $name = [System.Text.Encoding]::ASCII.GetString($monitor.UserFriendlyName).Trim([char]0)
            $info.Monitor = $name
        }

        # Refresh rate - use the real GPU we already found
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
    $script:notifyIcon.Text = "A.B.S.O. - Running Audit..."

    try {
        $tempFile = [System.IO.Path]::GetTempFileName()
        Start-Process -FilePath "python" -ArgumentList "-m", "abso", "audit", "--json" `
            -NoNewWindow -Wait -WorkingDirectory $script:ProjectRoot `
            -RedirectStandardOutput $tempFile

        $rawOutput = Get-Content $tempFile -Raw -ErrorAction SilentlyContinue
        Remove-Item $tempFile -Force -ErrorAction SilentlyContinue

        if ($rawOutput) {
            $json = $rawOutput | ConvertFrom-Json
            if ($json.success -and $json.data) {
                $issues = $json.data.issues
                $issueCount = if ($issues) { $issues.Count } else { 0 }
                if ($issueCount -eq 0) {
                    Show-Notification -Title "A.B.S.O. Audit" -Message "No issues found - system optimized!" -Type "Info"
                }
                else {
                    Show-Notification -Title "A.B.S.O. Audit" -Message "$issueCount issue(s) found. Run 'abso audit' for details." -Type "Warning"
                }
            }
        }
    }
    catch {
        Write-TrayLog "Audit failed: $($_.Exception.Message)" -Level "ERROR"
        Show-Notification -Title "A.B.S.O." -Message "Audit failed: $($_.Exception.Message)" -Type "Error"
    }

    Update-MenuState
}

function Open-BackupsFolder {
    $backupsPath = Join-Path $script:ProjectRoot "backups"
    if (Test-Path $backupsPath) {
        Start-Process "explorer.exe" -ArgumentList $backupsPath
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

function Toggle-Startup {
    $startupPath = [System.IO.Path]::Combine(
        [Environment]::GetFolderPath("Startup"),
        "ABSO-Tray.lnk"
    )

    if (Test-Path $startupPath) {
        # Remove from startup
        Remove-Item $startupPath -Force -ErrorAction SilentlyContinue
        Show-Notification -Title "A.B.S.O." -Message "Removed from Windows startup" -Type "Info"
        $script:startupItem.Text = "      Enable Auto-Start"
        $script:startupItem.Checked = $false
    }
    else {
        # Add to startup
        $installScript = Join-Path $script:ScriptDir "Install-Startup.ps1"
        if (Test-Path $installScript) {
            & $installScript
            Show-Notification -Title "A.B.S.O." -Message "Added to Windows startup" -Type "Info"
            $script:startupItem.Text = "      Disable Auto-Start"
            $script:startupItem.Checked = $true
        }
    }
}

function Get-LastBackupTime {
    $backupsPath = Join-Path $script:ProjectRoot "backups"
    if (Test-Path $backupsPath) {
        $latest = Get-ChildItem $backupsPath -Directory -ErrorAction SilentlyContinue |
            Sort-Object CreationTime -Descending | Select-Object -First 1
        if ($latest) {
            $age = (Get-Date) - $latest.CreationTime
            if ($age.TotalMinutes -lt 60) {
                return "$([int]$age.TotalMinutes)m ago"
            }
            elseif ($age.TotalHours -lt 24) {
                return "$([int]$age.TotalHours)h ago"
            }
            else {
                return "$([int]$age.TotalDays)d ago"
            }
        }
    }
    return "Never"
}

# ============================================================================
# MAIN
# ============================================================================

function Start-TrayApp {
    # Validate sound files at startup
    Test-SoundFilesExist | Out-Null

    $script:notifyIcon = New-Object System.Windows.Forms.NotifyIcon
    $script:notifyIcon.Icon = New-ABSOIcon
    $script:notifyIcon.Text = "A.B.S.O. - Ready"
    $script:notifyIcon.Visible = $true

    $script:activeProfile = $null
    $script:profileMenuItems = @()

    # Get system info
    $sysInfo = Get-SystemInfo

    # Context menu
    $menu = New-Object System.Windows.Forms.ContextMenuStrip
    $menu.BackColor = $script:Colors.Background
    $menu.ForeColor = $script:Colors.Text
    $menu.ShowImageMargin = $false
    $menu.ShowCheckMargin = $false
    $menu.Renderer = New-Object System.Windows.Forms.ToolStripProfessionalRenderer
    $menu.Renderer.RoundedEdges = $false

    # ═══════════════════════════════════════════════════════════════════════
    # HEADER SECTION
    # ═══════════════════════════════════════════════════════════════════════

    $header = New-Object System.Windows.Forms.ToolStripMenuItem
    $header.Text = "A.B.S.O.  v$($script:AppVersion)"
    $header.Enabled = $false
    $header.BackColor = $script:Colors.Background
    $header.ForeColor = $script:Colors.AccentGold
    $header.Font = New-Object System.Drawing.Font("Segoe UI", 10, [System.Drawing.FontStyle]::Bold)
    $menu.Items.Add($header) | Out-Null

    $subheader = New-Object System.Windows.Forms.ToolStripMenuItem
    $subheader.Text = "   Adaptive Battle Station Optimizer"
    $subheader.Enabled = $false
    $subheader.BackColor = $script:Colors.Background
    $subheader.ForeColor = $script:Colors.TextDim
    $subheader.Font = New-Object System.Drawing.Font("Segoe UI", 8)
    $menu.Items.Add($subheader) | Out-Null

    # ═══════════════════════════════════════════════════════════════════════
    # SYSTEM INFO SECTION
    # ═══════════════════════════════════════════════════════════════════════

    $sep0 = New-Object System.Windows.Forms.ToolStripSeparator
    $menu.Items.Add($sep0) | Out-Null

    $sysLabel = New-Object System.Windows.Forms.ToolStripMenuItem
    $sysLabel.Text = "  SYSTEM"
    $sysLabel.Enabled = $false
    $sysLabel.BackColor = $script:Colors.Background
    $sysLabel.ForeColor = $script:Colors.TextDim
    $sysLabel.Font = New-Object System.Drawing.Font("Segoe UI", 7.5, [System.Drawing.FontStyle]::Bold)
    $menu.Items.Add($sysLabel) | Out-Null

    $gpuInfo = New-Object System.Windows.Forms.ToolStripMenuItem
    $gpuInfo.Text = "      GPU: $($sysInfo.GPU)"
    $gpuInfo.Enabled = $false
    $gpuInfo.BackColor = $script:Colors.Background
    $gpuInfo.ForeColor = $script:Colors.Text
    $gpuInfo.Font = New-Object System.Drawing.Font("Consolas", 8)
    $menu.Items.Add($gpuInfo) | Out-Null

    $monInfo = New-Object System.Windows.Forms.ToolStripMenuItem
    $monInfo.Text = "      Display: $($sysInfo.Monitor) @ $($sysInfo.RefreshRate)"
    $monInfo.Enabled = $false
    $monInfo.BackColor = $script:Colors.Background
    $monInfo.ForeColor = $script:Colors.Text
    $monInfo.Font = New-Object System.Drawing.Font("Consolas", 8)
    $menu.Items.Add($monInfo) | Out-Null

    $script:statusItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $script:statusItem.Text = "      Status: Ready"
    $script:statusItem.Enabled = $false
    $script:statusItem.BackColor = $script:Colors.Background
    $script:statusItem.ForeColor = $script:Colors.AccentGreen
    $script:statusItem.Font = New-Object System.Drawing.Font("Consolas", 8)
    $menu.Items.Add($script:statusItem) | Out-Null

    # ═══════════════════════════════════════════════════════════════════════
    # PROFILES SECTION
    # ═══════════════════════════════════════════════════════════════════════

    $sep = New-Object System.Windows.Forms.ToolStripSeparator
    $menu.Items.Add($sep) | Out-Null

    $profilesLabel = New-Object System.Windows.Forms.ToolStripMenuItem
    $profilesLabel.Text = "  PROFILES"
    $profilesLabel.Enabled = $false
    $profilesLabel.BackColor = $script:Colors.Background
    $profilesLabel.ForeColor = $script:Colors.TextDim
    $profilesLabel.Font = New-Object System.Drawing.Font("Segoe UI", 7.5, [System.Drawing.FontStyle]::Bold)
    $menu.Items.Add($profilesLabel) | Out-Null

    # Group profiles by category
    $catProfiles = @{}
    foreach ($id in $script:Profiles.Keys) {
        $p = $script:Profiles[$id]
        if (-not $catProfiles.ContainsKey($p.Cat)) {
            $catProfiles[$p.Cat] = @()
        }
        $catProfiles[$p.Cat] += @{ Id = $id; Profile = $p }
    }

    # Add profiles by category
    foreach ($cat in $script:CategoryOrder) {
        if ($catProfiles.ContainsKey($cat)) {
            # Category header
            $catItem = New-Object System.Windows.Forms.ToolStripMenuItem
            $catItem.Text = "    $cat"
            $catItem.Enabled = $false
            $catItem.BackColor = $script:Colors.Background
            $catItem.ForeColor = $script:CategoryColors[$cat]
            $catItem.Font = New-Object System.Drawing.Font("Segoe UI", 8.5, [System.Drawing.FontStyle]::Bold)
            $menu.Items.Add($catItem) | Out-Null

            # Profile entries
            foreach ($entry in $catProfiles[$cat]) {
                $id = $entry.Id
                $p = $entry.Profile

                $item = New-Object System.Windows.Forms.ToolStripMenuItem
                $item.Text = "      $($p.Name)"
                $item.Tag = $id
                $item.BackColor = $script:Colors.Background
                $item.ForeColor = $script:Colors.Text
                $item.Font = New-Object System.Drawing.Font("Segoe UI", 9)

                # Build rich tooltip with description
                $tooltipText = "$($p.Sub)`n"
                if ($p.Desc) {
                    $tooltipText += "`n$($p.Desc)"
                }
                if ($p.Note) {
                    $tooltipText += "`n`n[$($p.Note)]"
                }
                $item.ToolTipText = $tooltipText.Trim()

                $item.Add_Click({
                    param($s, $ev)
                    Apply-Profile $s.Tag
                }.GetNewClosure())

                $menu.Items.Add($item) | Out-Null
                $script:profileMenuItems += $item
            }
        }
    }

    # ═══════════════════════════════════════════════════════════════════════
    # ACTIONS SECTION
    # ═══════════════════════════════════════════════════════════════════════

    $sep2 = New-Object System.Windows.Forms.ToolStripSeparator
    $menu.Items.Add($sep2) | Out-Null

    $actionsLabel = New-Object System.Windows.Forms.ToolStripMenuItem
    $actionsLabel.Text = "  ACTIONS"
    $actionsLabel.Enabled = $false
    $actionsLabel.BackColor = $script:Colors.Background
    $actionsLabel.ForeColor = $script:Colors.TextDim
    $actionsLabel.Font = New-Object System.Drawing.Font("Segoe UI", 7.5, [System.Drawing.FontStyle]::Bold)
    $menu.Items.Add($actionsLabel) | Out-Null

    # Restore Previous
    $script:restoreItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $script:restoreItem.Text = "      Restore Previous Settings"
    $script:restoreItem.Enabled = $false
    $script:restoreItem.BackColor = $script:Colors.Background
    $script:restoreItem.ForeColor = $script:Colors.Text
    $script:restoreItem.Font = New-Object System.Drawing.Font("Segoe UI", 9)
    $script:restoreItem.ToolTipText = "Restore the last backup before profile was applied"
    $script:restoreItem.Add_Click({ Restore-Settings })
    $menu.Items.Add($script:restoreItem) | Out-Null

    # Run Audit
    $auditItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $auditItem.Text = "      Run System Audit"
    $auditItem.BackColor = $script:Colors.Background
    $auditItem.ForeColor = $script:Colors.Text
    $auditItem.Font = New-Object System.Drawing.Font("Segoe UI", 9)
    $auditItem.ToolTipText = "Scan system for optimization issues"
    $auditItem.Add_Click({ Run-Audit })
    $menu.Items.Add($auditItem) | Out-Null

    # Open Backups
    $backupTime = Get-LastBackupTime
    $backupsItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $backupsItem.Text = "      Open Backups Folder"
    $backupsItem.BackColor = $script:Colors.Background
    $backupsItem.ForeColor = $script:Colors.Text
    $backupsItem.Font = New-Object System.Drawing.Font("Segoe UI", 9)
    $backupsItem.ToolTipText = "Last backup: $backupTime"
    $backupsItem.Add_Click({ Open-BackupsFolder })
    $menu.Items.Add($backupsItem) | Out-Null

    # ═══════════════════════════════════════════════════════════════════════
    # SETTINGS SECTION
    # ═══════════════════════════════════════════════════════════════════════

    $sep3 = New-Object System.Windows.Forms.ToolStripSeparator
    $menu.Items.Add($sep3) | Out-Null

    $settingsLabel = New-Object System.Windows.Forms.ToolStripMenuItem
    $settingsLabel.Text = "  SETTINGS"
    $settingsLabel.Enabled = $false
    $settingsLabel.BackColor = $script:Colors.Background
    $settingsLabel.ForeColor = $script:Colors.TextDim
    $settingsLabel.Font = New-Object System.Drawing.Font("Segoe UI", 7.5, [System.Drawing.FontStyle]::Bold)
    $menu.Items.Add($settingsLabel) | Out-Null

    # Auto-Start toggle
    $startupPath = [System.IO.Path]::Combine([Environment]::GetFolderPath("Startup"), "ABSO-Tray.lnk")
    $isStartupEnabled = Test-Path $startupPath

    $script:startupItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $script:startupItem.Text = if ($isStartupEnabled) { "      Disable Auto-Start" } else { "      Enable Auto-Start" }
    $script:startupItem.Checked = $isStartupEnabled
    $script:startupItem.BackColor = $script:Colors.Background
    $script:startupItem.ForeColor = $script:Colors.Text
    $script:startupItem.Font = New-Object System.Drawing.Font("Segoe UI", 9)
    $script:startupItem.ToolTipText = "Start A.B.S.O. Tray when Windows starts"
    $script:startupItem.Add_Click({ Toggle-Startup })
    $menu.Items.Add($script:startupItem) | Out-Null

    # Notifications toggle
    $script:notifyToggle = New-Object System.Windows.Forms.ToolStripMenuItem
    $script:notifyToggle.Text = "      Notifications"
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
    $menu.Items.Add($script:notifyToggle) | Out-Null

    # View Log
    $logItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $logItem.Text = "      View Log File"
    $logItem.BackColor = $script:Colors.Background
    $logItem.ForeColor = $script:Colors.TextDim
    $logItem.Font = New-Object System.Drawing.Font("Segoe UI", 9)
    $logItem.ToolTipText = $script:LogFile
    $logItem.Add_Click({ Open-LogFile })
    $menu.Items.Add($logItem) | Out-Null

    # ═══════════════════════════════════════════════════════════════════════
    # EXIT SECTION
    # ═══════════════════════════════════════════════════════════════════════

    $sep4 = New-Object System.Windows.Forms.ToolStripSeparator
    $menu.Items.Add($sep4) | Out-Null

    # Restart
    $restartItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $restartItem.Text = "  Restart Tray"
    $restartItem.BackColor = $script:Colors.Background
    $restartItem.ForeColor = $script:Colors.TextDim
    $restartItem.Font = New-Object System.Drawing.Font("Segoe UI", 9)
    $restartItem.Add_Click({
        if ($script:mutex) {
            try { $script:mutex.ReleaseMutex() } catch {}
            $script:mutex.Close()
            $script:mutex = $null
        }
        $vbsPath = Join-Path $script:ScriptDir "ABSO-Tray.vbs"
        if (Test-Path $vbsPath) {
            Start-Process "wscript.exe" -ArgumentList "`"$vbsPath`"" -WindowStyle Hidden
        }
        else {
            Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$PSCommandPath`"" -WindowStyle Hidden
        }
        Stop-ExistingWatcher
        $script:notifyIcon.Visible = $false
        [System.Windows.Forms.Application]::Exit()
    })
    $menu.Items.Add($restartItem) | Out-Null

    # Exit
    $exitItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $exitItem.Text = "  Exit"
    $exitItem.BackColor = $script:Colors.Background
    $exitItem.ForeColor = $script:Colors.TextDim
    $exitItem.Font = New-Object System.Drawing.Font("Segoe UI", 9)
    $exitItem.Add_Click({
        Stop-ExistingWatcher
        $script:notifyIcon.Visible = $false
        [System.Windows.Forms.Application]::Exit()
    })
    $menu.Items.Add($exitItem) | Out-Null

    $script:notifyIcon.ContextMenuStrip = $menu

    # Left-click shows menu
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

    # Restore state from previous session
    if (Test-Path $script:ActiveProfileFile) {
        try {
            $saved = Get-Content $script:ActiveProfileFile | ConvertFrom-Json
            if ($saved.ProfileId -and $script:Profiles.Contains($saved.ProfileId)) {
                $script:activeProfile = $saved.ProfileId
                Write-TrayLog "Restored active profile: $($saved.ProfileId)"
                Update-MenuState
            }
        }
        catch {
            Write-TrayLog "Failed to restore state: $($_.Exception.Message)" -Level "WARN"
        }
    }

    [System.Windows.Forms.Application]::Run()
    $script:notifyIcon.Dispose()
}

# ============================================================================
# RUN
# ============================================================================

try {
    Write-TrayLog "ABSO Tray starting (PID: $PID)"
    Start-TrayApp
    Write-TrayLog "ABSO Tray exiting normally"
}
finally {
    if ($script:mutex) {
        try { $script:mutex.ReleaseMutex() } catch {}
        $script:mutex.Close()
        $script:mutex = $null
    }
}
