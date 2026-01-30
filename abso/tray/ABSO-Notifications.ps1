# ABSO-Notifications.ps1 - Enhanced notification system for A.B.S.O. tray
# Provides toast notifications with action buttons and progress overlays

# ============================================================================
# PROGRESS OVERLAY
# ============================================================================

$script:ProgressForm = $null
$script:ProgressLabel = $null
$script:ProgressBar = $null
$script:ProgressTimer = $null
$script:ProgressAngle = 0

function Show-ProgressOverlay {
    <#
    .SYNOPSIS
    Shows a small floating progress window during profile application.
    .PARAMETER Title
    The title text (e.g. "Applying Rivals 2: Online")
    .PARAMETER StepText
    The current step text (e.g. "Applying NVIDIA settings...")
    #>
    param(
        [string]$Title = "Applying Profile...",
        [string]$StepText = "Initializing..."
    )

    Close-ProgressOverlay

    $form = New-Object System.Windows.Forms.Form
    $form.Text = ""
    $form.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::None
    $form.BackColor = [System.Drawing.Color]::FromArgb(255, 28, 28, 32)
    $form.Size = New-Object System.Drawing.Size(320, 120)
    $form.StartPosition = [System.Windows.Forms.FormStartPosition]::Manual
    $form.TopMost = $true
    $form.ShowInTaskbar = $false
    $form.Opacity = 0.95

    # Position bottom-right above taskbar
    $screen = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
    $form.Location = New-Object System.Drawing.Point(
        ($screen.Right - $form.Width - 16),
        ($screen.Bottom - $form.Height - 16)
    )

    # Rounded corners via region
    $form.Add_Paint({
        param($s, $e)
        $g = $e.Graphics
        $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias

        # Border glow
        $borderPen = New-Object System.Drawing.Pen(
            [System.Drawing.Color]::FromArgb(60, 140, 120, 220), 1
        )
        $g.DrawRectangle($borderPen, 0, 0, $s.Width - 1, $s.Height - 1)
        $borderPen.Dispose()
    })

    # Title label
    $titleLabel = New-Object System.Windows.Forms.Label
    $titleLabel.Text = $Title
    $titleLabel.ForeColor = [System.Drawing.Color]::FromArgb(255, 220, 180, 70)
    $titleLabel.Font = New-Object System.Drawing.Font("Segoe UI", 10, [System.Drawing.FontStyle]::Bold)
    $titleLabel.Location = New-Object System.Drawing.Point(16, 12)
    $titleLabel.Size = New-Object System.Drawing.Size(288, 24)
    $titleLabel.BackColor = [System.Drawing.Color]::Transparent
    $form.Controls.Add($titleLabel)

    # Step label
    $stepLabel = New-Object System.Windows.Forms.Label
    $stepLabel.Text = $StepText
    $stepLabel.ForeColor = [System.Drawing.Color]::FromArgb(255, 180, 180, 180)
    $stepLabel.Font = New-Object System.Drawing.Font("Segoe UI", 9)
    $stepLabel.Location = New-Object System.Drawing.Point(16, 40)
    $stepLabel.Size = New-Object System.Drawing.Size(288, 20)
    $stepLabel.BackColor = [System.Drawing.Color]::Transparent
    $form.Controls.Add($stepLabel)

    # Progress bar (custom drawn)
    $progressPanel = New-Object System.Windows.Forms.Panel
    $progressPanel.Location = New-Object System.Drawing.Point(16, 72)
    $progressPanel.Size = New-Object System.Drawing.Size(288, 6)
    $progressPanel.BackColor = [System.Drawing.Color]::FromArgb(255, 50, 50, 55)

    $progressFill = New-Object System.Windows.Forms.Panel
    $progressFill.Location = New-Object System.Drawing.Point(0, 0)
    $progressFill.Size = New-Object System.Drawing.Size(0, 6)
    $progressFill.BackColor = [System.Drawing.Color]::FromArgb(255, 140, 120, 220)
    $progressPanel.Controls.Add($progressFill)
    $form.Controls.Add($progressPanel)

    # Animated indeterminate progress
    $timer = New-Object System.Windows.Forms.Timer
    $timer.Interval = 100
    $script:ProgressAngle = 0
    $timer.Add_Tick({
        $script:ProgressAngle = ($script:ProgressAngle + 3) % 288
        if ($script:ProgressForm -and $script:ProgressBar) {
            $script:ProgressBar.Location = New-Object System.Drawing.Point($script:ProgressAngle, 0)
            $script:ProgressBar.Size = New-Object System.Drawing.Size(80, 6)
            if (($script:ProgressAngle + 80) -gt 288) {
                $script:ProgressBar.Size = New-Object System.Drawing.Size((288 - $script:ProgressAngle), 6)
            }
        }
    })
    $timer.Start()

    # Cancel link
    $cancelLabel = New-Object System.Windows.Forms.Label
    $cancelLabel.Text = "Cancel"
    $cancelLabel.ForeColor = [System.Drawing.Color]::FromArgb(255, 120, 120, 120)
    $cancelLabel.Font = New-Object System.Drawing.Font("Segoe UI", 8)
    $cancelLabel.Location = New-Object System.Drawing.Point(260, 92)
    $cancelLabel.Size = New-Object System.Drawing.Size(50, 20)
    $cancelLabel.BackColor = [System.Drawing.Color]::Transparent
    $cancelLabel.Cursor = [System.Windows.Forms.Cursors]::Hand
    $cancelLabel.Add_MouseEnter({ $this.ForeColor = [System.Drawing.Color]::FromArgb(255, 200, 200, 200) })
    $cancelLabel.Add_MouseLeave({ $this.ForeColor = [System.Drawing.Color]::FromArgb(255, 120, 120, 120) })
    $form.Controls.Add($cancelLabel)

    $script:ProgressForm = $form
    $script:ProgressLabel = $stepLabel
    $script:ProgressBar = $progressFill
    $script:ProgressTimer = $timer

    $form.Show()
}

function Update-ProgressOverlay {
    <#
    .SYNOPSIS
    Updates the step text in the progress overlay.
    #>
    param([string]$StepText)

    if ($script:ProgressForm -and $script:ProgressLabel) {
        $script:ProgressLabel.Text = $StepText
        $script:ProgressForm.Refresh()
    }
}

function Close-ProgressOverlay {
    <#
    .SYNOPSIS
    Closes and disposes the progress overlay.
    #>
    if ($script:ProgressTimer) {
        $script:ProgressTimer.Stop()
        $script:ProgressTimer.Dispose()
        $script:ProgressTimer = $null
    }
    if ($script:ProgressForm) {
        $script:ProgressForm.Close()
        $script:ProgressForm.Dispose()
        $script:ProgressForm = $null
    }
    $script:ProgressLabel = $null
    $script:ProgressBar = $null
}

# ============================================================================
# TOAST NOTIFICATIONS
# ============================================================================

function Show-ABSONotification {
    <#
    .SYNOPSIS
    Shows a rich notification. Uses balloon tips with enhanced formatting.
    .PARAMETER Title
    Notification title.
    .PARAMETER Message
    Notification message body.
    .PARAMETER Type
    One of: Info, Warning, Error, Success
    .PARAMETER NotifyIcon
    The NotifyIcon instance to use.
    .PARAMETER Duration
    Duration in milliseconds (default 3000).
    #>
    param(
        [string]$Title,
        [string]$Message,
        [ValidateSet("Info", "Warning", "Error", "Success")]
        [string]$Type = "Info",
        [System.Windows.Forms.NotifyIcon]$NotifyIcon,
        [int]$Duration = 3000
    )

    if (-not $NotifyIcon) { return }

    # Update tooltip text
    $maxLen = [Math]::Min(63, "$Title - $Message".Length)
    $NotifyIcon.Text = "$Title - $Message".Substring(0, $maxLen)

    $icon = switch ($Type) {
        "Warning" { [System.Windows.Forms.ToolTipIcon]::Warning }
        "Error"   { [System.Windows.Forms.ToolTipIcon]::Error }
        "Success" { [System.Windows.Forms.ToolTipIcon]::Info }
        default   { [System.Windows.Forms.ToolTipIcon]::Info }
    }

    $NotifyIcon.ShowBalloonTip($Duration, $Title, $Message, $icon)
}

# ============================================================================
# STATUS BAR
# ============================================================================

function New-StatusBarItem {
    <#
    .SYNOPSIS
    Creates a status bar menu item showing last action, current game, etc.
    .PARAMETER LastAction
    Description of the last action performed.
    .PARAMETER LastActionTime
    Timestamp of last action.
    .PARAMETER CurrentGame
    Name of currently detected game (or $null).
    .PARAMETER BackupTime
    Last backup timestamp string.
    #>
    param(
        [string]$LastAction = "Ready",
        [string]$LastActionTime = "",
        [string]$CurrentGame = "",
        [string]$BackupTime = ""
    )

    $parts = @()
    if ($LastAction) { $parts += $LastAction }
    if ($CurrentGame) { $parts += "Game: $CurrentGame" }
    if ($BackupTime) { $parts += "Backup: $BackupTime" }

    $text = $parts -join "  |  "

    $item = New-Object System.Windows.Forms.ToolStripMenuItem
    $item.Text = "  $text"
    $item.Enabled = $false
    $item.BackColor = [System.Drawing.Color]::FromArgb(255, 24, 24, 28)
    $item.ForeColor = [System.Drawing.Color]::FromArgb(255, 100, 100, 110)
    $item.Font = New-Object System.Drawing.Font("Consolas", 7.5)
    return $item
}
