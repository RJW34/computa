# ABSO-Tray.ps1 - Ultra-lightweight system tray for A.B.S.O.
# Memory: ~25-30MB | CPU: Near-zero when idle
# Left-click shows profile menu, applies via CLI, monitors game lifecycle

param([switch]$Hidden)

# ============================================================================
# ADMIN ELEVATION CHECK
# ============================================================================
# A.B.S.O. requires admin privileges to modify system settings.
# If not running as admin, re-launch with elevation.

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    # Re-launch as admin
    $scriptPath = $PSCommandPath
    try {
        Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`" -Hidden" -Verb RunAs -WindowStyle Hidden
    } catch {
        # User declined UAC or other error - show message and exit
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

# ============================================================================
# NOTIFICATION SYSTEM
# ============================================================================
# Notifications disabled - Windows shows ugly "Windows PowerShell" attribution
# for script-based apps. Instead, we update the tray tooltip with status.
# Set to $true to re-enable balloon notifications if desired.

$script:EnableBalloonNotifications = $true

function Show-Notification {
    param(
        [string]$Title,
        [string]$Message,
        [ValidateSet("Info", "Warning", "Error")]
        [string]$Type = "Info"
    )

    # Update tray tooltip with the message
    $script:notifyIcon.Text = "$Title - $Message".Substring(0, [Math]::Min(63, "$Title - $Message".Length))

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
# Uses a global mutex to ensure only one tray instance runs at a time.
# If another instance is already running, this one exits silently.

$script:mutexName = "Global\ABSO_Tray_SingleInstance_v1"
$script:createdNew = $false
try {
    $script:mutex = New-Object System.Threading.Mutex($true, $script:mutexName, [ref]$script:createdNew)
} catch {
    # Mutex creation failed - another instance likely holds it
    exit 0
}

if (-not $script:createdNew) {
    # Another instance already owns the mutex - exit silently
    if ($script:mutex) {
        $script:mutex.Close()
        $script:mutex = $null
    }
    exit 0
}

# Also kill any orphaned PowerShell processes running this script
# (handles edge cases where mutex wasn't properly released)
$currentPID = $PID
$scriptName = "ABSO-Tray.ps1"
Get-Process -Name "powershell" -ErrorAction SilentlyContinue | Where-Object {
    $_.Id -ne $currentPID -and
    $_.MainWindowTitle -eq "" -and
    (Get-WmiObject Win32_Process -Filter "ProcessId=$($_.Id)" -ErrorAction SilentlyContinue).CommandLine -like "*$scriptName*"
} | ForEach-Object {
    Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
}

# Paths
$script:ScriptDir = $PSScriptRoot
$script:ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$script:WatcherPIDFile = Join-Path $env:TEMP "abso_watcher.pid"
$script:ActiveProfileFile = Join-Path $env:TEMP "abso_active_profile.json"

# Profile definitions (minimal - just what tray needs)
# Using OLED editions for monitors with OLED displays
$script:Profiles = @{
    "pacdeluxe-oled" = @{
        Name = "PACDeluxe - Pokemon Auto Chess (OLED)"
        Short = "PAC"
        Executables = @("PACDeluxe.exe", "pac-deluxe.exe")
    }
    "rivals2-oled" = @{
        Name = "Rivals of Aether 2 (OLED)"
        Short = "Rivals 2"
        Executables = @("Rivals2-Win64-Shipping.exe", "RivalsofAether2.exe", "Rivals2.exe")
    }
    "rivals2-oled-vrr" = @{
        Name = "Rivals of Aether 2 (OLED + G-Sync)"
        Short = "Rivals 2 VRR"
        Executables = @("Rivals2-Win64-Shipping.exe", "RivalsofAether2.exe", "Rivals2.exe")
    }
    "slippi-melee-oled" = @{
        Name = "Super Smash Bros. Melee (Slippi) (OLED)"
        Short = "Slippi Melee"
        Executables = @("Slippi Dolphin.exe", "Dolphin.exe")
    }
    "cod-bo7" = @{
        Name = "Call of Duty: Black Ops 7"
        Short = "CoD BO7"
        Executables = @("cod.exe", "BlackOps7.exe")
    }
}

# Create A.B.S.O. icon (16x16 lightning bolt - represents optimization)
function New-ABSOIcon {
    $bmp = New-Object System.Drawing.Bitmap(16, 16)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $g.Clear([System.Drawing.Color]::Transparent)

    # Lightning bolt shape (gold/yellow for "optimization power")
    $brush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(255, 200, 50))
    $points = @(
        [System.Drawing.Point]::new(10, 1),
        [System.Drawing.Point]::new(4, 8),
        [System.Drawing.Point]::new(8, 8),
        [System.Drawing.Point]::new(6, 15),
        [System.Drawing.Point]::new(12, 7),
        [System.Drawing.Point]::new(8, 7)
    )
    $g.FillPolygon($brush, $points)

    # Dark outline for visibility
    $pen = New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb(100, 50, 0), 1)
    $g.DrawPolygon($pen, $points)

    $g.Dispose()
    $brush.Dispose()
    $pen.Dispose()

    return [System.Drawing.Icon]::FromHandle($bmp.GetHicon())
}

# Kill any existing watcher
function Stop-ExistingWatcher {
    if (Test-Path $script:WatcherPIDFile) {
        try {
            $pid = [int](Get-Content $script:WatcherPIDFile -ErrorAction SilentlyContinue)
            if ($pid -gt 0) {
                Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
            }
        } catch {}
        Remove-Item $script:WatcherPIDFile -Force -ErrorAction SilentlyContinue
    }
}

# Spawn game watcher
function Start-GameWatcher {
    param([string]$ProfileId, [string[]]$Executables)

    Stop-ExistingWatcher

    $exeList = $Executables -join ','
    $watcherPath = Join-Path $script:ScriptDir "ABSO-Watcher.ps1"
    $trayPath = Join-Path $script:ScriptDir "ABSO-Tray.ps1"

    # Start watcher in background
    $proc = Start-Process powershell -ArgumentList @(
        "-NoProfile", "-WindowStyle", "Hidden", "-ExecutionPolicy", "Bypass",
        "-File", "`"$watcherPath`"",
        "-ExeList", "`"$exeList`"",
        "-TrayPID", $PID,
        "-TrayScript", "`"$trayPath`""
    ) -WindowStyle Hidden -PassThru

    # Save watcher PID
    $proc.Id | Out-File $script:WatcherPIDFile -Force

    # Save active profile for reference
    @{ ProfileId = $ProfileId; Executables = $Executables } |
        ConvertTo-Json | Out-File $script:ActiveProfileFile -Force
}

# NOTE: Priority boosting removed - SpecialK handles this for Rivals 2
# See rivals2_oled_vrr.py for SpecialK configuration details

# Apply profile via CLI
function Apply-Profile {
    param([string]$ProfileId)

    $profile = $script:Profiles[$ProfileId]
    $script:notifyIcon.Text = "A.B.S.O. - Applying..."

    try {
        # Call CLI with JSON output (capture stdout only, ignore stderr warnings)
        # Use Start-Process for cleaner output capture
        $tempFile = [System.IO.Path]::GetTempFileName()
        $proc = Start-Process -FilePath "python" -ArgumentList "-m", "abso", "apply", $ProfileId, "--json" `
            -NoNewWindow -Wait -PassThru -WorkingDirectory $script:ProjectRoot `
            -RedirectStandardOutput $tempFile -RedirectStandardError "$tempFile.err"

        $rawOutput = Get-Content $tempFile -Raw -ErrorAction SilentlyContinue
        Remove-Item $tempFile -Force -ErrorAction SilentlyContinue
        Remove-Item "$tempFile.err" -Force -ErrorAction SilentlyContinue

        if (-not $rawOutput) {
            throw "No output from CLI"
        }

        $json = $rawOutput | ConvertFrom-Json

        if ($json.success -and $json.data.success) {
            $data = $json.data

            # Build notification message
            $actions = @()
            if ($data.requires_reboot) {
                $actions += "Restart PC required"
            }
            if ($data.in_game_settings -and $data.in_game_settings.Count -gt 0) {
                $actions += "See settings report"
            }

            $message = "Profile applied: $($profile.Short)"
            if ($actions.Count -gt 0) {
                $message += "`n" + ($actions -join ", ")
            }

            Show-Notification -Title "A.B.S.O." -Message $message -Type "Info"

            # Start game watcher
            Start-GameWatcher -ProfileId $ProfileId -Executables $profile.Executables

            # Note: For Rivals 2, SpecialK handles priority boosting
            # Launch via SKIF for optimal latency (see rivals2_oled_vrr profile docs)

            $script:notifyIcon.Text = "A.B.S.O. - $($profile.Short) active"
            $script:activeProfile = $ProfileId
            Update-MenuState

        } else {
            $errMsg = if ($json.error) { $json.error } else { "Unknown error" }
            Show-Notification -Title "A.B.S.O. Error" -Message "Failed: $errMsg" -Type "Error"
            $script:notifyIcon.Text = "A.B.S.O."
        }
    } catch {
        $errText = $_.Exception.Message
        if ($errText.Length -gt 100) { $errText = $errText.Substring(0, 100) + "..." }
        Show-Notification -Title "A.B.S.O. Error" -Message "Failed: $errText" -Type "Error"
        $script:notifyIcon.Text = "A.B.S.O."
    }
}

# Restore previous settings
function Restore-Settings {
    $script:notifyIcon.Text = "A.B.S.O. - Restoring..."

    try {
        # Use Start-Process for cleaner output capture
        $tempFile = [System.IO.Path]::GetTempFileName()
        $proc = Start-Process -FilePath "python" -ArgumentList "-m", "abso", "restore", "latest", "--json" `
            -NoNewWindow -Wait -PassThru -WorkingDirectory $script:ProjectRoot `
            -RedirectStandardOutput $tempFile -RedirectStandardError "$tempFile.err"

        $rawOutput = Get-Content $tempFile -Raw -ErrorAction SilentlyContinue
        Remove-Item $tempFile -Force -ErrorAction SilentlyContinue
        Remove-Item "$tempFile.err" -Force -ErrorAction SilentlyContinue

        if (-not $rawOutput) {
            throw "No output from CLI"
        }

        $json = $rawOutput | ConvertFrom-Json

        if ($json.success) {
            Show-Notification -Title "A.B.S.O." -Message "Settings restored to previous state" -Type "Info"
            Stop-ExistingWatcher
            $script:activeProfile = $null
            $script:notifyIcon.Text = "A.B.S.O."
            Update-MenuState
        } else {
            Show-Notification -Title "A.B.S.O." -Message "Restore failed: $($json.error)" -Type "Warning"
        }
    } catch {
        $errText = $_.Exception.Message
        if ($errText.Length -gt 100) { $errText = $errText.Substring(0, 100) + "..." }
        Show-Notification -Title "A.B.S.O." -Message "Restore failed: $errText" -Type "Warning"
    }
    $script:notifyIcon.Text = "A.B.S.O."
}

# Update menu checkmarks and tooltip
function Update-MenuState {
    foreach ($item in $script:profileMenuItems) {
        $item.Checked = ($item.Tag -eq $script:activeProfile)
    }
    $script:restoreItem.Enabled = ($script:activeProfile -ne $null)

    # Update tooltip with active profile
    if ($script:activeProfile) {
        $profileName = $script:Profiles[$script:activeProfile].Short
        $script:notifyIcon.Text = "A.B.S.O. - $profileName"
    } else {
        $script:notifyIcon.Text = "A.B.S.O."
    }
}

# Main tray setup
function Start-TrayApp {
    $script:notifyIcon = New-Object System.Windows.Forms.NotifyIcon
    $script:notifyIcon.Icon = New-ABSOIcon
    $script:notifyIcon.Text = "A.B.S.O."
    $script:notifyIcon.Visible = $true

    $script:activeProfile = $null
    $script:profileMenuItems = @()

    # Context menu
    $menu = New-Object System.Windows.Forms.ContextMenuStrip

    # Header (disabled, just label)
    $header = New-Object System.Windows.Forms.ToolStripMenuItem
    $header.Text = "Select Profile"
    $header.Enabled = $false
    $menu.Items.Add($header) | Out-Null

    $menu.Items.Add((New-Object System.Windows.Forms.ToolStripSeparator)) | Out-Null

    # Profile items (OLED editions where available)
    foreach ($id in @("pacdeluxe-oled", "rivals2-oled", "rivals2-oled-vrr", "slippi-melee-oled", "cod-bo7")) {
        $profile = $script:Profiles[$id]
        $item = New-Object System.Windows.Forms.ToolStripMenuItem
        $item.Text = $profile.Name
        $item.Tag = $id
        $item.Add_Click({
            param($sender, $e)
            Apply-Profile $sender.Tag
        }.GetNewClosure())
        $menu.Items.Add($item) | Out-Null
        $script:profileMenuItems += $item
    }

    $menu.Items.Add((New-Object System.Windows.Forms.ToolStripSeparator)) | Out-Null

    # Restore option
    $script:restoreItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $script:restoreItem.Text = "Restore Previous Settings"
    $script:restoreItem.Enabled = $false
    $script:restoreItem.Add_Click({ Restore-Settings })
    $menu.Items.Add($script:restoreItem) | Out-Null

    $menu.Items.Add((New-Object System.Windows.Forms.ToolStripSeparator)) | Out-Null

    # Note: Boost Priority removed - SpecialK handles priority for Rivals 2

    # Restart tray
    $restartItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $restartItem.Text = "Restart Tray"
    $restartItem.Add_Click({
        # Release mutex FIRST so new instance can acquire it
        if ($script:mutex) {
            try { $script:mutex.ReleaseMutex() } catch {}
            $script:mutex.Close()
            $script:mutex = $null
        }
        # Now launch new instance
        $trayPath = Join-Path $script:ScriptDir "ABSO-Tray.vbs"
        Start-Process "wscript.exe" -ArgumentList "`"$trayPath`"" -WindowStyle Hidden
        # Exit current instance
        Stop-ExistingWatcher
        $script:notifyIcon.Visible = $false
        [System.Windows.Forms.Application]::Exit()
    })
    $menu.Items.Add($restartItem) | Out-Null

    # Exit
    $exitItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $exitItem.Text = "Exit"
    $exitItem.Add_Click({
        Stop-ExistingWatcher
        $script:notifyIcon.Visible = $false
        [System.Windows.Forms.Application]::Exit()
    })
    $menu.Items.Add($exitItem) | Out-Null

    $script:notifyIcon.ContextMenuStrip = $menu

    # Left-click shows menu at cursor
    $script:notifyIcon.Add_Click({
        param($sender, $e)
        if ($e.Button -eq [System.Windows.Forms.MouseButtons]::Left) {
            # Use reflection to invoke private ShowContextMenu method
            $mi = $script:notifyIcon.GetType().GetMethod(
                "ShowContextMenu",
                [System.Reflection.BindingFlags]::Instance -bor [System.Reflection.BindingFlags]::NonPublic
            )
            $mi.Invoke($script:notifyIcon, $null)
        }
    })

    # Check if we had an active profile (for restart scenarios)
    if (Test-Path $script:ActiveProfileFile) {
        try {
            $saved = Get-Content $script:ActiveProfileFile | ConvertFrom-Json
            if ($saved.ProfileId -and $script:Profiles.ContainsKey($saved.ProfileId)) {
                $script:activeProfile = $saved.ProfileId
                $script:notifyIcon.Text = "A.B.S.O. - $($script:Profiles[$saved.ProfileId].Short) active"
                Update-MenuState
            }
        } catch {}
    }

    [System.Windows.Forms.Application]::Run()

    # Cleanup
    $script:notifyIcon.Dispose()
}

# Run
try {
    Start-TrayApp
} finally {
    # Release mutex so new instances can start
    if ($script:mutex) {
        try {
            $script:mutex.ReleaseMutex()
        } catch {
            # May fail if we didn't own it - that's ok
        }
        $script:mutex.Close()
        $script:mutex = $null
    }
}
