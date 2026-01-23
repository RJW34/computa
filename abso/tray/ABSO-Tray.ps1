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

function Play-SuccessSound {
    <#
    .SYNOPSIS
    Plays the success sound effect at 20% volume when a profile is applied.
    #>
    try {
        if (Test-Path $script:SoundFile) {
            $mediaPlayer = New-Object System.Windows.Media.MediaPlayer
            $mediaPlayer.Open([Uri]$script:SoundFile)
            $mediaPlayer.Volume = 0.20  # 20% volume
            $mediaPlayer.Play()
            Write-TrayLog "Playing success sound"

            # Don't block - let it play in background
            # MediaPlayer will be garbage collected after playback
        }
        else {
            Write-TrayLog "Sound file not found: $($script:SoundFile)" -Level "WARN"
        }
    }
    catch {
        Write-TrayLog "Failed to play sound: $($_.Exception.Message)" -Level "WARN"
    }
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

$script:Profiles = [ordered]@{
    "productivity-oled" = @{
        Name     = "Productivity"
        Sub      = "OLED + HDR"
        Cat      = "Productivity"
        Note     = "Browsing, Coding"
        Exes     = @("Code.exe", "devenv.exe", "chrome.exe", "firefox.exe", "msedge.exe")
    }
    "rivals2-offline"   = @{
        Name     = "Rivals 2"
        Sub      = "OFFLINE / Training"
        Cat      = "Fighting"
        Note     = "Max latency reduction"
        Exes     = @("Rivals2-Win64-Shipping.exe", "RivalsofAether2.exe", "Rivals2.exe")
    }
    "rivals2-online"    = @{
        Name     = "Rivals 2"
        Sub      = "ONLINE / Matchmaking"
        Cat      = "Fighting"
        Note     = "Rollback-safe"
        Exes     = @("Rivals2-Win64-Shipping.exe", "RivalsofAether2.exe", "Rivals2.exe")
    }
    "rivals2-oled-vrr"  = @{
        Name     = "Rivals 2"
        Sub      = "G-Sync + SpecialK"
        Cat      = "Fighting"
        Note     = "Requires SpecialK"
        Exes     = @("Rivals2-Win64-Shipping.exe", "RivalsofAether2.exe", "Rivals2.exe")
    }
    "rivals2-oled-vrr-multimon" = @{
        Name     = "Rivals 2"
        Sub      = "G-Sync MultiMon"
        Cat      = "Fighting"
        Note     = "Borderless windowed"
        Exes     = @("Rivals2-Win64-Shipping.exe", "RivalsofAether2.exe", "Rivals2.exe")
    }
    "rivals2-oled"      = @{
        Name     = "Rivals 2"
        Sub      = "No-Sync"
        Cat      = "Fighting"
        Note     = "Minimum latency"
        Exes     = @("Rivals2-Win64-Shipping.exe", "RivalsofAether2.exe", "Rivals2.exe")
    }
    "slippi-melee-vrr"  = @{
        Name     = "Slippi Melee"
        Sub      = "G-Sync"
        Cat      = "Fighting"
        Note     = "Tear-free 60fps"
        Exes     = @("Slippi Dolphin.exe", "Dolphin.exe")
    }
    "slippi-melee-oled" = @{
        Name     = "Slippi Melee"
        Sub      = "No-Sync"
        Cat      = "Fighting"
        Note     = "Fixed 60fps"
        Exes     = @("Slippi Dolphin.exe", "Dolphin.exe")
    }
    "ryujinx-ssbu-vrr"  = @{
        Name     = "SSBU / HDR"
        Sub      = "G-Sync"
        Cat      = "Fighting"
        Note     = "Ryujinx emulator"
        Exes     = @("Ryujinx.exe", "Ryujinx.Ava.exe", "Ryujinx.Headless.SDL2.exe")
    }
    "ryujinx-ssbu-oled" = @{
        Name     = "SSBU / HDR"
        Sub      = "OLED"
        Cat      = "Fighting"
        Note     = "Ryujinx emulator"
        Exes     = @("Ryujinx.exe", "Ryujinx.Ava.exe", "Ryujinx.Headless.SDL2.exe")
    }
    "diablo4-oled-vrr"  = @{
        Name     = "Diablo 4"
        Sub      = "G-Sync"
        Cat      = "ARPG"
        Note     = "Native Reflex"
        Exes     = @("Diablo IV.exe")
    }
    "diablo4-oled"      = @{
        Name     = "Diablo 4"
        Sub      = "OLED"
        Cat      = "ARPG"
        Note     = "Low latency"
        Exes     = @("Diablo IV.exe")
    }
    "pacdeluxe-oled"    = @{
        Name     = "PACDeluxe"
        Sub      = "OLED"
        Cat      = "Other"
        Note     = ""
        Exes     = @("PACDeluxe.exe", "pac-deluxe.exe")
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
            Show-Notification -Title "A.B.S.O." -Message "Failed: $err" -Type "Error"
        }
    }
    catch {
        Write-TrayLog "Apply-Profile exception: $($_.Exception.Message)" -Level "ERROR"
        Show-Notification -Title "A.B.S.O." -Message "Error: $($_.Exception.Message)" -Type "Error"
    }
}

function Restore-Settings {
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
            $item.Text = "  >>  $($p.Name)  -  $($p.Sub)  <<"
            $item.ForeColor = $script:Colors.AccentGreen
        }
        else {
            $item.Text = "      $($p.Name)  -  $($p.Sub)"
            $item.ForeColor = $script:Colors.Text
        }
    }
    $script:restoreItem.Enabled = ($null -ne $script:activeProfile)

    if ($script:activeProfile) {
        $p = $script:Profiles[$script:activeProfile]
        $script:notifyIcon.Icon = New-ABSOIcon -Active
        $script:notifyIcon.Text = "A.B.S.O. - $($p.Name) active"
    }
    else {
        $script:notifyIcon.Icon = New-ABSOIcon
        $script:notifyIcon.Text = "A.B.S.O. - Ready"
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
# MAIN
# ============================================================================

function Start-TrayApp {
    $script:notifyIcon = New-Object System.Windows.Forms.NotifyIcon
    $script:notifyIcon.Icon = New-ABSOIcon
    $script:notifyIcon.Text = "A.B.S.O. - Ready"
    $script:notifyIcon.Visible = $true

    $script:activeProfile = $null
    $script:profileMenuItems = @()

    # Context menu
    $menu = New-Object System.Windows.Forms.ContextMenuStrip
    $menu.BackColor = $script:Colors.Background
    $menu.ForeColor = $script:Colors.Text
    $menu.ShowImageMargin = $false
    $menu.ShowCheckMargin = $false
    $menu.Renderer = New-Object System.Windows.Forms.ToolStripProfessionalRenderer

    # Override renderer colors
    $menu.Renderer.RoundedEdges = $false

    # Header
    $header = New-Object System.Windows.Forms.ToolStripMenuItem
    $header.Text = "A.B.S.O."
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

    $sep = New-Object System.Windows.Forms.ToolStripSeparator
    $sep.BackColor = $script:Colors.Separator
    $menu.Items.Add($sep) | Out-Null

    # Group profiles
    $catProfiles = @{}
    foreach ($id in $script:Profiles.Keys) {
        $p = $script:Profiles[$id]
        if (-not $catProfiles.ContainsKey($p.Cat)) {
            $catProfiles[$p.Cat] = @()
        }
        $catProfiles[$p.Cat] += @{ Id = $id; Profile = $p }
    }

    # Add by category
    foreach ($cat in $script:CategoryOrder) {
        if ($catProfiles.ContainsKey($cat)) {
            # Category label
            $catItem = New-Object System.Windows.Forms.ToolStripMenuItem
            $catItem.Text = "  $cat"
            $catItem.Enabled = $false
            $catItem.BackColor = $script:Colors.Background
            $catItem.ForeColor = $script:CategoryColors[$cat]
            $catItem.Font = New-Object System.Drawing.Font("Segoe UI", 8.5, [System.Drawing.FontStyle]::Bold)
            $menu.Items.Add($catItem) | Out-Null

            # Profiles
            foreach ($entry in $catProfiles[$cat]) {
                $id = $entry.Id
                $p = $entry.Profile

                $item = New-Object System.Windows.Forms.ToolStripMenuItem
                $item.Text = "      $($p.Name)  -  $($p.Sub)"
                $item.Tag = $id
                $item.BackColor = $script:Colors.Background
                $item.ForeColor = $script:Colors.Text
                $item.Font = New-Object System.Drawing.Font("Segoe UI", 9)

                if ($p.Note) {
                    $item.ToolTipText = $p.Note
                }

                $item.Add_Click({
                    param($s, $ev)
                    Apply-Profile $s.Tag
                }.GetNewClosure())

                $menu.Items.Add($item) | Out-Null
                $script:profileMenuItems += $item
            }
        }
    }

    $sep2 = New-Object System.Windows.Forms.ToolStripSeparator
    $sep2.BackColor = $script:Colors.Separator
    $menu.Items.Add($sep2) | Out-Null

    # Restore
    $script:restoreItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $script:restoreItem.Text = "  Restore Previous"
    $script:restoreItem.Enabled = $false
    $script:restoreItem.BackColor = $script:Colors.Background
    $script:restoreItem.ForeColor = $script:Colors.Text
    $script:restoreItem.Font = New-Object System.Drawing.Font("Segoe UI", 9)
    $script:restoreItem.Add_Click({ Restore-Settings })
    $menu.Items.Add($script:restoreItem) | Out-Null

    $sep3 = New-Object System.Windows.Forms.ToolStripSeparator
    $sep3.BackColor = $script:Colors.Separator
    $menu.Items.Add($sep3) | Out-Null

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

    # Restore state
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
