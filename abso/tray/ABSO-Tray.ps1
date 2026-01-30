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

# ============================================================================
# LOAD MODULES
# ============================================================================

$script:ScriptDir = $PSScriptRoot
. (Join-Path $script:ScriptDir "ABSO-Icons.ps1")
. (Join-Path $script:ScriptDir "ABSO-Notifications.ps1")
. (Join-Path $script:ScriptDir "ABSO-Settings.ps1")
. (Join-Path $script:ScriptDir "ABSO-QuickPanel.ps1")

# ============================================================================
# SOUND EFFECTS
# ============================================================================

$script:SoundFile = Join-Path $PSScriptRoot "pokemon-red_blue_yellow-save-game-sound-effect.mp3"
$script:FailSoundFile = Join-Path $PSScriptRoot "hit-weak-not-very-effective.mp3"
$script:MediaPlayer = $null

function Get-MediaPlayer {
    if ($null -eq $script:MediaPlayer) {
        $script:MediaPlayer = New-Object System.Windows.Media.MediaPlayer
        Register-ObjectEvent -InputObject $script:MediaPlayer -EventName MediaEnded -Action {
            $script:MediaPlayer.Close()
        } | Out-Null
    }
    return $script:MediaPlayer
}

function Play-SuccessSound {
    try {
        if (-not $script:TrayConfig.soundEnabled) { return }
        if (Test-Path $script:SoundFile) {
            $player = Get-MediaPlayer
            $player.Close()
            $player.Open([Uri]$script:SoundFile)
            $player.Volume = $script:TrayConfig.soundVolume
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
    try {
        if (-not $script:TrayConfig.soundEnabled) { return }
        if (Test-Path $script:FailSoundFile) {
            $player = Get-MediaPlayer
            $player.Close()
            $player.Open([Uri]$script:FailSoundFile)
            $player.Volume = [Math]::Min(1.0, $script:TrayConfig.soundVolume * 3)
            $player.Play()
            Write-TrayLog "Playing fail sound"
        }
    }
    catch {
        Write-TrayLog "Failed to play fail sound: $($_.Exception.Message)" -Level "WARN"
    }
}

function Test-SoundFilesExist {
    $allPresent = $true
    if (-not (Test-Path $script:SoundFile)) {
        Write-TrayLog "SUCCESS SOUND FILE MISSING: $($script:SoundFile)" -Level "WARN"
        $allPresent = $false
    }
    if (-not (Test-Path $script:FailSoundFile)) {
        Write-TrayLog "FAIL SOUND FILE MISSING: $($script:FailSoundFile)" -Level "WARN"
        $allPresent = $false
    }
    if ($allPresent) { Write-TrayLog "Sound files validated" }
    return $allPresent
}

# ============================================================================
# DARK THEME COLORS
# ============================================================================

$script:Colors = @{
    Background      = [System.Drawing.Color]::FromArgb(255, 32, 32, 32)
    BackgroundDark  = [System.Drawing.Color]::FromArgb(255, 24, 24, 28)
    Hover           = [System.Drawing.Color]::FromArgb(255, 55, 55, 58)
    HoverBright     = [System.Drawing.Color]::FromArgb(255, 65, 65, 70)
    Text            = [System.Drawing.Color]::FromArgb(255, 220, 220, 220)
    TextDim         = [System.Drawing.Color]::FromArgb(255, 140, 140, 140)
    TextDisabled    = [System.Drawing.Color]::FromArgb(255, 90, 90, 90)
    Border          = [System.Drawing.Color]::FromArgb(255, 60, 60, 60)
    Separator       = [System.Drawing.Color]::FromArgb(255, 55, 55, 55)
    AccentGold      = [System.Drawing.Color]::FromArgb(255, 220, 180, 70)
    AccentGreen     = [System.Drawing.Color]::FromArgb(255, 90, 200, 120)
    AccentBlue      = [System.Drawing.Color]::FromArgb(255, 80, 160, 230)
    AccentPurple    = [System.Drawing.Color]::FromArgb(255, 140, 120, 220)
    FavoriteStar    = [System.Drawing.Color]::FromArgb(255, 255, 210, 70)
    CatFighting     = [System.Drawing.Color]::FromArgb(255, 230, 120, 120)
    CatARPG         = [System.Drawing.Color]::FromArgb(255, 180, 150, 220)
    CatShooter      = [System.Drawing.Color]::FromArgb(255, 120, 180, 220)
    CatOther        = [System.Drawing.Color]::FromArgb(255, 150, 200, 150)
    CatProd         = [System.Drawing.Color]::FromArgb(255, 220, 190, 120)
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

$script:ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$script:WatcherPIDFile = Join-Path $env:TEMP "abso_watcher.pid"
$script:ActiveProfileFile = Join-Path $env:TEMP "abso_active_profile.json"

# ============================================================================
# PROFILE DEFINITIONS
# ============================================================================

$script:AppVersion = "2.0.0"

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
# ICON STATE MANAGEMENT
# ============================================================================

$script:IconState = "Idle"
$script:ApplyAnimTimer = $null

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

    if ($State -eq "Applying") {
        # Start animation timer
        if (-not $script:ApplyAnimTimer) {
            $script:ApplyAnimTimer = New-Object System.Windows.Forms.Timer
            $script:ApplyAnimTimer.Interval = 300
            $script:ApplyAnimTimer.Add_Tick({
                $oldIcon = $script:notifyIcon.Icon
                $script:notifyIcon.Icon = New-StateIcon -State "Applying"
                if ($oldIcon) {
                    try { $oldIcon.Dispose() } catch {}
                }
            })
        }
        $script:ApplyAnimTimer.Start()
        $newIcon = New-StateIcon -State "Applying"
        $oldIcon = $script:notifyIcon.Icon
        $script:notifyIcon.Icon = $newIcon
        if ($oldIcon) {
            try { $oldIcon.Dispose() } catch {}
        }
    }
    else {
        # Stop animation
        if ($script:ApplyAnimTimer) {
            $script:ApplyAnimTimer.Stop()
        }
        $newIcon = New-StateIcon -State $State
        $oldIcon = $script:notifyIcon.Icon
        $script:notifyIcon.Icon = $newIcon
        if ($oldIcon) {
            try { $oldIcon.Dispose() } catch {}
        }
    }
}

# ============================================================================
# APPLY / RESTORE
# ============================================================================

function Apply-Profile {
    param([string]$ProfileId)

    Write-TrayLog "Apply-Profile called with: $ProfileId"
    $profile = $script:Profiles[$ProfileId]

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

            Play-SuccessSound
            Set-IconState -State "Active"
            Show-Notification -Title "A.B.S.O." -Message $msg -Type "Info"
            Start-GameWatcher -ProfileId $ProfileId -Executables $profile.Exes

            $script:activeProfile = $ProfileId
            $script:LastAction = "Applied: $($profile.Name)"
            $script:LastActionTime = Get-Date -Format "HH:mm"

            # Record in history
            $script:TrayConfig = Add-ProfileHistory -ProfileId $ProfileId -ProfileName $profile.Name -Config $script:TrayConfig

            Update-MenuState
            Update-QuickPanel -Favorites $script:TrayConfig.favorites -Profiles $script:Profiles -ActiveProfile $script:activeProfile -OnApply { param($id) Apply-Profile $id }
        }
        else {
            $err = if ($json.error) { $json.error } else { "Unknown error" }
            Write-TrayLog "Profile apply failed: $err" -Level "ERROR"
            Close-ProgressOverlay
            Play-FailSound
            Set-IconState -State "Error"
            Show-Notification -Title "A.B.S.O." -Message "Failed: $err" -Type "Error"
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

        Start-Process -FilePath "python" -ArgumentList "-m", "abso", "restore", "latest", "--json" `
            -NoNewWindow -Wait -WorkingDirectory $script:ProjectRoot `
            -RedirectStandardOutput $tempFile -RedirectStandardError $errFile

        $rawOutput = Get-Content $tempFile -Raw -ErrorAction SilentlyContinue
        Remove-Item $tempFile -Force -ErrorAction SilentlyContinue
        Remove-Item $errFile -Force -ErrorAction SilentlyContinue

        if (-not $rawOutput) { throw "No output" }

        $json = $rawOutput | ConvertFrom-Json

        if ($json.success) {
            Close-ProgressOverlay
            Show-Notification -Title "A.B.S.O." -Message "Settings restored" -Type "Info"
            Stop-ExistingWatcher
            # Clean up stale state file
            if (Test-Path $script:ActiveProfileFile) {
                Remove-Item $script:ActiveProfileFile -Force -ErrorAction SilentlyContinue
            }
            $script:activeProfile = $null
            $script:LastAction = "Restored settings"
            $script:LastActionTime = Get-Date -Format "HH:mm"
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
        $isFav = Test-Favorite -ProfileId $item.Tag -Config $script:TrayConfig
        $starPrefix = if ($isFav) { "[*] " } else { "      " }

        if ($isActive) {
            $item.Text = "  >>  $($p.Name)"
            $item.ForeColor = $script:Colors.AccentGreen
            $item.Font = New-Object System.Drawing.Font("Segoe UI", 9, [System.Drawing.FontStyle]::Bold)
        }
        else {
            $item.Text = "$starPrefix$($p.Name)"
            $item.ForeColor = $script:Colors.Text
            $item.Font = New-Object System.Drawing.Font("Segoe UI", 9)
        }
    }
    $script:restoreItem.Enabled = ($null -ne $script:activeProfile)

    if ($script:activeProfile) {
        $p = $script:Profiles[$script:activeProfile]
        $tooltipText = "A.B.S.O. - $($p.Name)"
        if ($tooltipText.Length -gt 63) {
            $tooltipText = $tooltipText.Substring(0, 60) + "..."
        }
        $script:notifyIcon.Text = $tooltipText

        if ($script:statusItem) {
            $script:statusItem.Text = "      Active: $($p.Name)"
            $script:statusItem.ForeColor = $script:Colors.AccentGreen
        }
    }
    else {
        $script:notifyIcon.Text = "A.B.S.O. - Ready"

        if ($script:statusItem) {
            $script:statusItem.Text = "      Status: Ready"
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

function Open-ConfigFolder {
    $configDir = Join-Path $env:APPDATA "ABSO"
    if (-not (Test-Path $configDir)) {
        New-Item -Path $configDir -ItemType Directory -Force | Out-Null
    }
    Start-Process "explorer.exe" -ArgumentList $configDir
}

function Toggle-Startup {
    $startupPath = [System.IO.Path]::Combine(
        [Environment]::GetFolderPath("Startup"),
        "ABSO-Tray.lnk"
    )

    if (Test-Path $startupPath) {
        Remove-Item $startupPath -Force -ErrorAction SilentlyContinue
        Show-Notification -Title "A.B.S.O." -Message "Removed from Windows startup" -Type "Info"
        $script:startupItem.Text = "      Enable Auto-Start"
        $script:startupItem.Checked = $false
    }
    else {
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

    # Load config
    $script:TrayConfig = Read-TrayConfig
    $script:LastAction = $null
    $script:LastActionTime = $null
    $script:AuditIssueCount = 0

    $script:notifyIcon = New-Object System.Windows.Forms.NotifyIcon
    Set-IconState -State "Idle"
    $script:notifyIcon.Text = "A.B.S.O. - Ready"
    $script:notifyIcon.Visible = $true

    $script:activeProfile = $null
    $script:profileMenuItems = @()

    # Get system info
    $sysInfo = Get-SystemInfo

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
        Register-ObjectEvent -InputObject $script:HotkeyWindow -EventName HotkeyPressed -Action {
            $hotkeyId = $Event.SourceEventArgs
            $action = Get-HotkeyAction -HotkeyId $hotkeyId
            if ($action) {
                & $action
            }
        } | Out-Null

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
    $menu.ShowImageMargin = $false
    $menu.ShowCheckMargin = $false
    $menu.Renderer = New-Object System.Windows.Forms.ToolStripProfessionalRenderer
    $menu.Renderer.RoundedEdges = $false

    # ─── HEADER ───

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

    # ─── SYSTEM INFO ───

    $menu.Items.Add((New-Object System.Windows.Forms.ToolStripSeparator)) | Out-Null

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

    # Audit status (hidden by default)
    $script:auditStatusItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $script:auditStatusItem.Text = ""
    $script:auditStatusItem.Enabled = $false
    $script:auditStatusItem.BackColor = $script:Colors.Background
    $script:auditStatusItem.ForeColor = $script:Colors.TextDim
    $script:auditStatusItem.Font = New-Object System.Drawing.Font("Consolas", 8)
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
            # Show/hide category headers
            foreach ($catItem in $script:categoryHeaders) {
                $cat = $catItem.Tag
                $hasVisible = $false
                foreach ($pItem in $script:profileMenuItems) {
                    if ($pItem.Visible -and $script:Profiles[$pItem.Tag].Cat -eq $cat) {
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
        $favLabel.Text = "  FAVORITES"
        $favLabel.Enabled = $false
        $favLabel.BackColor = $script:Colors.Background
        $favLabel.ForeColor = $script:Colors.FavoriteStar
        $favLabel.Font = New-Object System.Drawing.Font("Segoe UI", 7.5, [System.Drawing.FontStyle]::Bold)
        $menu.Items.Add($favLabel) | Out-Null
        $script:favSectionLabel = $favLabel

        foreach ($favId in $favProfiles) {
            $p = $script:Profiles[$favId]
            $item = New-Object System.Windows.Forms.ToolStripMenuItem
            $item.Text = "  [*] $($p.Name)"
            $item.Tag = $favId
            $item.BackColor = $script:Colors.Background
            $item.ForeColor = $script:Colors.Text
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
        $recentLabel.Text = "  RECENT"
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
            $item = New-Object System.Windows.Forms.ToolStripMenuItem
            $item.Text = "      $($p.Name)"
            $item.Tag = $rId
            $item.BackColor = $script:Colors.Background
            $item.ForeColor = $script:Colors.TextDim
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

    # ─── PROFILES ───

    $menu.Items.Add((New-Object System.Windows.Forms.ToolStripSeparator)) | Out-Null

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

    $script:categoryHeaders = @()

    foreach ($cat in $script:CategoryOrder) {
        if ($catProfiles.ContainsKey($cat)) {
            $catItem = New-Object System.Windows.Forms.ToolStripMenuItem
            $catItem.Text = "    $cat"
            $catItem.Tag = $cat
            $catItem.Enabled = $false
            $catItem.BackColor = $script:Colors.Background
            $catItem.ForeColor = $script:CategoryColors[$cat]
            $catItem.Font = New-Object System.Drawing.Font("Segoe UI", 8.5, [System.Drawing.FontStyle]::Bold)
            $menu.Items.Add($catItem) | Out-Null
            $script:categoryHeaders += $catItem

            foreach ($entry in $catProfiles[$cat]) {
                $id = $entry.Id
                $p = $entry.Profile
                $isFav = Test-Favorite -ProfileId $id -Config $script:TrayConfig

                $item = New-Object System.Windows.Forms.ToolStripMenuItem
                $starPrefix = if ($isFav) { "[*] " } else { "      " }
                $item.Text = "$starPrefix$($p.Name)"
                $item.Tag = $id
                $item.BackColor = $script:Colors.Background
                $item.ForeColor = $script:Colors.Text
                $item.Font = New-Object System.Drawing.Font("Segoe UI", 9)

                $tooltipText = "$($p.Sub)`n"
                if ($p.Desc) { $tooltipText += "`n$($p.Desc)" }
                if ($isFav) { $tooltipText += "`n`n[Favorited]" }
                $item.ToolTipText = $tooltipText.Trim()

                # Left-click applies profile
                $item.Add_Click({
                    param($s, $ev)
                    Apply-Profile $s.Tag
                }.GetNewClosure())

                $menu.Items.Add($item) | Out-Null
                $script:profileMenuItems += $item
            }
        }
    }

    # ─── ACTIONS ───

    $menu.Items.Add((New-Object System.Windows.Forms.ToolStripSeparator)) | Out-Null

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

    # Backups submenu
    $backupTime = Get-LastBackupTime
    $backupsItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $backupsItem.Text = "      Backups ($backupTime)"
    $backupsItem.BackColor = $script:Colors.Background
    $backupsItem.ForeColor = $script:Colors.Text
    $backupsItem.Font = New-Object System.Drawing.Font("Segoe UI", 9)

    # Backup submenu items
    $openBackupsItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $openBackupsItem.Text = "Open Backups Folder"
    $openBackupsItem.BackColor = $script:Colors.Background
    $openBackupsItem.ForeColor = $script:Colors.Text
    $openBackupsItem.Font = New-Object System.Drawing.Font("Segoe UI", 9)
    $openBackupsItem.Add_Click({ Open-BackupsFolder })
    $backupsItem.DropDownItems.Add($openBackupsItem) | Out-Null

    $backupsItem.DropDownItems.Add((New-Object System.Windows.Forms.ToolStripSeparator)) | Out-Null

    # Recent backups
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
                Start-Process -FilePath "python" -ArgumentList "-m", "abso", "restore", $capturedName, "--json" `
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

    $menu.Items.Add($backupsItem) | Out-Null

    # Toggle Quick Panel
    $quickPanelItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $quickPanelItem.Text = "      Quick Panel"
    $quickPanelItem.BackColor = $script:Colors.Background
    $quickPanelItem.ForeColor = $script:Colors.Text
    $quickPanelItem.Font = New-Object System.Drawing.Font("Segoe UI", 9)
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
        $quickPanelItem.Checked = $script:QuickPanelVisible
        Save-TrayConfig $script:TrayConfig
    })
    $menu.Items.Add($quickPanelItem) | Out-Null

    # ─── SETTINGS ───

    $menu.Items.Add((New-Object System.Windows.Forms.ToolStripSeparator)) | Out-Null

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

    # Sound toggle
    $soundToggle = New-Object System.Windows.Forms.ToolStripMenuItem
    $soundToggle.Text = "      Sound Effects"
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
    $menu.Items.Add($soundToggle) | Out-Null

    # Open Settings Panel
    $settingsPanelItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $settingsPanelItem.Text = "      Open Settings..."
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
    $menu.Items.Add($settingsPanelItem) | Out-Null

    # View Log
    $logItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $logItem.Text = "      View Log File"
    $logItem.BackColor = $script:Colors.Background
    $logItem.ForeColor = $script:Colors.TextDim
    $logItem.Font = New-Object System.Drawing.Font("Segoe UI", 9)
    $logItem.ToolTipText = $script:LogFile
    $logItem.Add_Click({ Open-LogFile })
    $menu.Items.Add($logItem) | Out-Null

    # Open Config Folder
    $configFolderItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $configFolderItem.Text = "      Open Config Folder"
    $configFolderItem.BackColor = $script:Colors.Background
    $configFolderItem.ForeColor = $script:Colors.TextDim
    $configFolderItem.Font = New-Object System.Drawing.Font("Segoe UI", 9)
    $configFolderItem.Add_Click({ Open-ConfigFolder })
    $menu.Items.Add($configFolderItem) | Out-Null

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
        if ($script:HotkeyWindow) { Unregister-GlobalHotkeys -WindowHandle $script:HotkeyWindow.Handle }
        Close-QuickPanel
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
    $exitItem.Add_Click({
        if ($script:HotkeyWindow) { Unregister-GlobalHotkeys -WindowHandle $script:HotkeyWindow.Handle }
        Close-QuickPanel
        Close-ProgressOverlay
        Stop-ExistingWatcher
        $script:notifyIcon.Visible = $false
        [System.Windows.Forms.Application]::Exit()
    })
    $menu.Items.Add($exitItem) | Out-Null

    $script:notifyIcon.ContextMenuStrip = $menu

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

    # ─── SCROLL WHEEL SUPPORT ───

    $script:scrollIndex = 0
    $script:scrollProfiles = @($script:Profiles.Keys)
    $script:scrollTimer = $null

    $script:notifyIcon.Add_MouseClick({
        param($s, $ev)
        # Mouse wheel events don't come through NotifyIcon directly in WinForms
        # This is handled through the hidden form's message loop instead
    })

    # ─── RESTORE STATE ───

    if (Test-Path $script:ActiveProfileFile) {
        try {
            $saved = Get-Content $script:ActiveProfileFile | ConvertFrom-Json
            if ($saved.ProfileId -and $script:Profiles.Contains($saved.ProfileId)) {
                $script:activeProfile = $saved.ProfileId
                Write-TrayLog "Restored active profile: $($saved.ProfileId)"
                Set-IconState -State "Active"
                Update-MenuState
            }
        }
        catch {
            Write-TrayLog "Failed to restore state: $($_.Exception.Message)" -Level "WARN"
        }
    }

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

    [System.Windows.Forms.Application]::Run()
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
finally {
    if ($script:ApplyAnimTimer) {
        $script:ApplyAnimTimer.Stop()
        $script:ApplyAnimTimer.Dispose()
    }
    Close-ProgressOverlay
    Close-QuickPanel
    Stop-ExistingWatcher
    # Clean up active profile state file
    if (Test-Path $script:ActiveProfileFile) {
        Remove-Item $script:ActiveProfileFile -Force -ErrorAction SilentlyContinue
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
    if ($script:mutex) {
        try { $script:mutex.ReleaseMutex() } catch {}
        $script:mutex.Close()
        $script:mutex = $null
    }
}
