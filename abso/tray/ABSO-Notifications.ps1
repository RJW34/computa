# ABSO-Notifications.ps1 - v2.0 Enhanced notification system for A.B.S.O. tray
# Custom dark-themed toast notifications, animated progress overlay,
# fade-in/fade-out transitions, DWM integration

# ============================================================================
# THEMED TOAST NOTIFICATIONS (replaces balloon tips)
# ============================================================================

$script:ToastForm = $null
$script:ToastDismissTimer = $null
$script:ToastFadeTimer = $null
$script:ToastDismissBarTimer = $null
$script:ToastDismissBar = $null

function Show-ThemedToast {
    <#
    .SYNOPSIS
    Shows a modern dark-themed floating toast notification.
    Replaces standard balloon tips with a visually consistent panel.
    .PARAMETER Title
    Toast title text.
    .PARAMETER Message
    Toast body message.
    .PARAMETER Type
    One of: Info, Warning, Error, Success. Controls accent color.
    .PARAMETER Duration
    Auto-dismiss time in milliseconds (default 4000).
    #>
    param(
        [string]$Title = "A.B.S.O.",
        [string]$Message = "",
        [ValidateSet("Info", "Warning", "Error", "Success")]
        [string]$Type = "Info",
        [int]$Duration = 4000
    )

    Close-ThemedToast

    # Accent color per notification type
    $accentColor = switch ($Type) {
        "Success" { [System.Drawing.Color]::FromArgb(255, 80, 210, 120) }
        "Warning" { [System.Drawing.Color]::FromArgb(255, 240, 180, 60) }
        "Error"   { [System.Drawing.Color]::FromArgb(255, 220, 75, 75) }
        default   { [System.Drawing.Color]::FromArgb(255, 90, 160, 235) }
    }

    # Symbol per type
    $symbol = switch ($Type) {
        "Success" { [string][char]0x2713 }
        "Warning" { "!" }
        "Error"   { [string][char]0x2717 }
        default   { "i" }
    }

    # Calculate form height based on message length
    $msgLines = [Math]::Ceiling($Message.Length / 48)
    $formHeight = [Math]::Max(88, 58 + ($msgLines * 18))
    $formHeight = [Math]::Min($formHeight, 160)

    $form = New-Object System.Windows.Forms.Form
    $form.Text = ""
    $form.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::None
    $form.BackColor = [System.Drawing.Color]::FromArgb(255, 26, 26, 30)
    $form.Size = New-Object System.Drawing.Size(380, $formHeight)
    $form.StartPosition = [System.Windows.Forms.FormStartPosition]::Manual
    $form.TopMost = $true
    $form.ShowInTaskbar = $false
    $form.Opacity = 0

    # Position bottom-right above taskbar
    $screen = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
    $form.Location = New-Object System.Drawing.Point(
        ($screen.Right - $form.Width - 16),
        ($screen.Bottom - $form.Height - 16)
    )

    # Custom paint: border, accent lines, status dot with glow
    $capturedAccent = $accentColor
    $capturedHeight = $formHeight
    $form.Add_Paint({
        param($s, $e)
        $g = $e.Graphics
        $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias

        # Outer border with subtle accent tint
        $borderPen = New-Object System.Drawing.Pen(
            [System.Drawing.Color]::FromArgb(35, $capturedAccent.R, $capturedAccent.G, $capturedAccent.B), 1
        )
        $g.DrawRectangle($borderPen, 0, 0, ($s.Width - 1), ($s.Height - 1))
        $borderPen.Dispose()

        # Top accent gradient line (bright left -> fade right)
        try {
            $topBrush = New-Object System.Drawing.Drawing2D.LinearGradientBrush(
                (New-Object System.Drawing.Point(0, 0)),
                (New-Object System.Drawing.Point($s.Width, 0)),
                [System.Drawing.Color]::FromArgb(220, $capturedAccent.R, $capturedAccent.G, $capturedAccent.B),
                [System.Drawing.Color]::FromArgb(15, $capturedAccent.R, $capturedAccent.G, $capturedAccent.B)
            )
            $g.FillRectangle($topBrush, 0, 0, $s.Width, 2)
            $topBrush.Dispose()
        } catch {
            $topPen = New-Object System.Drawing.Pen(
                [System.Drawing.Color]::FromArgb(160, $capturedAccent.R, $capturedAccent.G, $capturedAccent.B), 2
            )
            $g.DrawLine($topPen, 0, 0, $s.Width, 0)
            $topPen.Dispose()
        }

        # Left accent bar (vertical gradient: bright center -> fade edges)
        try {
            $leftBrush = New-Object System.Drawing.Drawing2D.LinearGradientBrush(
                (New-Object System.Drawing.Point(0, 4)),
                (New-Object System.Drawing.Point(0, ($capturedHeight - 4))),
                [System.Drawing.Color]::FromArgb(30, $capturedAccent.R, $capturedAccent.G, $capturedAccent.B),
                [System.Drawing.Color]::FromArgb(30, $capturedAccent.R, $capturedAccent.G, $capturedAccent.B)
            )
            $blend = New-Object System.Drawing.Drawing2D.ColorBlend(3)
            $blend.Colors = @(
                [System.Drawing.Color]::FromArgb(30, $capturedAccent.R, $capturedAccent.G, $capturedAccent.B),
                [System.Drawing.Color]::FromArgb(180, $capturedAccent.R, $capturedAccent.G, $capturedAccent.B),
                [System.Drawing.Color]::FromArgb(30, $capturedAccent.R, $capturedAccent.G, $capturedAccent.B)
            )
            $blend.Positions = @([float]0.0, [float]0.4, [float]1.0)
            $leftBrush.InterpolationColors = $blend
            $g.FillRectangle($leftBrush, 0, 3, 3, ($capturedHeight - 6))
            $leftBrush.Dispose()
        } catch {
            $barBrush = New-Object System.Drawing.SolidBrush(
                [System.Drawing.Color]::FromArgb(140, $capturedAccent.R, $capturedAccent.G, $capturedAccent.B)
            )
            $g.FillRectangle($barBrush, 0, 3, 3, ($capturedHeight - 6))
            $barBrush.Dispose()
        }

        # Status dot glow (larger, semi-transparent)
        $glowBrush = New-Object System.Drawing.SolidBrush(
            [System.Drawing.Color]::FromArgb(25, $capturedAccent.R, $capturedAccent.G, $capturedAccent.B)
        )
        $g.FillEllipse($glowBrush, 10, 12, 18, 18)
        $glowBrush.Dispose()

        # Status dot (solid)
        $dotBrush = New-Object System.Drawing.SolidBrush($capturedAccent)
        $g.FillEllipse($dotBrush, 15, 17, 8, 8)
        $dotBrush.Dispose()

        # Dot highlight (specular)
        $specBrush = New-Object System.Drawing.SolidBrush(
            [System.Drawing.Color]::FromArgb(80, 255, 255, 255)
        )
        $g.FillEllipse($specBrush, 16, 18, 3, 3)
        $specBrush.Dispose()
    }.GetNewClosure())

    # Title label
    $titleLabel = New-Object System.Windows.Forms.Label
    $titleLabel.Text = $Title
    $titleLabel.ForeColor = [System.Drawing.Color]::FromArgb(255, 240, 240, 245)
    $titleLabel.Font = New-Object System.Drawing.Font("Segoe UI Semibold", 10)
    $titleLabel.Location = New-Object System.Drawing.Point(32, 10)
    $titleLabel.Size = New-Object System.Drawing.Size(332, 22)
    $titleLabel.BackColor = [System.Drawing.Color]::Transparent
    $form.Controls.Add($titleLabel)

    # Message label
    $msgLabel = New-Object System.Windows.Forms.Label
    $msgLabel.Text = $Message
    $msgLabel.ForeColor = [System.Drawing.Color]::FromArgb(255, 165, 165, 175)
    $msgLabel.Font = New-Object System.Drawing.Font("Segoe UI", 9)
    $msgLabel.Location = New-Object System.Drawing.Point(32, 34)
    $msgLabel.Size = New-Object System.Drawing.Size(334, ($formHeight - 48))
    $msgLabel.BackColor = [System.Drawing.Color]::Transparent
    $form.Controls.Add($msgLabel)

    # Dismiss countdown bar at the very bottom
    $dismissBar = New-Object System.Windows.Forms.Panel
    $dismissBar.Location = New-Object System.Drawing.Point(0, ($formHeight - 3))
    $dismissBar.Size = New-Object System.Drawing.Size(380, 3)
    $dismissBar.BackColor = [System.Drawing.Color]::FromArgb(100, $accentColor.R, $accentColor.G, $accentColor.B)
    $form.Controls.Add($dismissBar)
    $script:ToastDismissBar = $dismissBar

    # Click to dismiss
    $form.Add_Click({ Close-ThemedToast })
    $titleLabel.Add_Click({ Close-ThemedToast })
    $msgLabel.Add_Click({ Close-ThemedToast })

    $script:ToastForm = $form
    $form.Show()

    # Apply DWM effects (rounded corners, dark mode, shadow)
    try {
        if ("DwmHelper" -as [type]) {
            Apply-DwmWindowEffects -Form $form -CornerStyle 3 -BorderColorRGB @(
                $accentColor.R, $accentColor.G, $accentColor.B
            )
        }
    } catch {}

    # Fade-in animation: opacity 0 -> 0.97
    $script:ToastFadeTimer = New-Object System.Windows.Forms.Timer
    $script:ToastFadeTimer.Interval = 16
    $script:ToastFadeTimer.Add_Tick({
        try {
            if ($script:ToastForm -and -not $script:ToastForm.IsDisposed) {
                $newOpacity = $script:ToastForm.Opacity + 0.10
                if ($newOpacity -ge 0.97) {
                    $script:ToastForm.Opacity = 0.97
                    $script:ToastFadeTimer.Stop()
                }
                else {
                    $script:ToastForm.Opacity = $newOpacity
                }
            }
            else {
                $script:ToastFadeTimer.Stop()
            }
        } catch { try { $script:ToastFadeTimer.Stop() } catch {} }
    })
    $script:ToastFadeTimer.Start()

    # Auto-dismiss timer
    $script:ToastDismissTimer = New-Object System.Windows.Forms.Timer
    $script:ToastDismissTimer.Interval = $Duration
    $script:ToastDismissTimer.Add_Tick({
        try {
            $script:ToastDismissTimer.Stop()
            # Start fade-out
            if ($script:ToastFadeTimer) {
                try { $script:ToastFadeTimer.Stop(); $script:ToastFadeTimer.Dispose() } catch {}
            }
            $script:ToastFadeTimer = New-Object System.Windows.Forms.Timer
            $script:ToastFadeTimer.Interval = 16
            $script:ToastFadeTimer.Add_Tick({
                try {
                    if ($script:ToastForm -and -not $script:ToastForm.IsDisposed) {
                        $newOpacity = $script:ToastForm.Opacity - 0.08
                        if ($newOpacity -le 0.02) {
                            Close-ThemedToast
                        }
                        else {
                            $script:ToastForm.Opacity = $newOpacity
                        }
                    }
                    else {
                        $script:ToastFadeTimer.Stop()
                    }
                } catch { try { $script:ToastFadeTimer.Stop() } catch {} }
            })
            $script:ToastFadeTimer.Start()
        } catch { try { $script:ToastDismissTimer.Stop() } catch {} }
    })
    $script:ToastDismissTimer.Start()

    # Dismiss bar countdown animation (shrinks from full width to 0)
    $script:ToastDismissBarTimer = New-Object System.Windows.Forms.Timer
    $script:ToastDismissBarTimer.Interval = 50
    $script:ToastDismissBarStart = Get-Date
    $script:ToastDismissBarDuration = $Duration
    $capturedDismissBar = $dismissBar
    $script:ToastDismissBarTimer.Add_Tick({
        try {
            $elapsed = ((Get-Date) - $script:ToastDismissBarStart).TotalMilliseconds
            $pct = 1.0 - [Math]::Min(1.0, $elapsed / $script:ToastDismissBarDuration)
            $newWidth = [Math]::Max(0, [int]($pct * 380))
            if ($capturedDismissBar -and -not $capturedDismissBar.IsDisposed) {
                $capturedDismissBar.Size = New-Object System.Drawing.Size($newWidth, 3)
            }
            if ($pct -le 0) {
                $script:ToastDismissBarTimer.Stop()
            }
        } catch { try { $script:ToastDismissBarTimer.Stop() } catch {} }
    })
    $script:ToastDismissBarTimer.Start()
}

function Close-ThemedToast {
    <#
    .SYNOPSIS
    Closes and disposes the themed toast notification and all associated timers.
    #>
    if ($script:ToastDismissBarTimer) {
        try { $script:ToastDismissBarTimer.Stop(); $script:ToastDismissBarTimer.Dispose() } catch {}
        $script:ToastDismissBarTimer = $null
    }
    if ($script:ToastFadeTimer) {
        try { $script:ToastFadeTimer.Stop(); $script:ToastFadeTimer.Dispose() } catch {}
        $script:ToastFadeTimer = $null
    }
    if ($script:ToastDismissTimer) {
        try { $script:ToastDismissTimer.Stop(); $script:ToastDismissTimer.Dispose() } catch {}
        $script:ToastDismissTimer = $null
    }
    if ($script:ToastForm -and -not $script:ToastForm.IsDisposed) {
        try {
            $script:ToastForm.Hide()
            [System.Windows.Forms.Application]::DoEvents()
            $script:ToastForm.Close()
            $script:ToastForm.Dispose()
        } catch {}
        $script:ToastForm = $null
    }
    $script:ToastDismissBar = $null
}

# ============================================================================
# PROGRESS OVERLAY (Enhanced v2.0)
# ============================================================================

$script:ProgressForm = $null
$script:ProgressLabel = $null
$script:ProgressBar = $null
$script:ProgressTimer = $null
$script:ProgressAngle = 0
$script:ProgressShimmerOffset = 0

function Show-ProgressOverlay {
    <#
    .SYNOPSIS
    Shows a modern floating progress window during profile application.
    Features gradient shimmer progress bar, fade-in animation, DWM effects.
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
    $form.BackColor = [System.Drawing.Color]::FromArgb(255, 22, 22, 26)
    $form.Size = New-Object System.Drawing.Size(380, 140)
    $form.StartPosition = [System.Windows.Forms.FormStartPosition]::Manual
    $form.TopMost = $true
    $form.ShowInTaskbar = $false
    $form.Opacity = 0

    # Position bottom-right above taskbar
    $screen = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
    $form.Location = New-Object System.Drawing.Point(
        ($screen.Right - $form.Width - 16),
        ($screen.Bottom - $form.Height - 16)
    )

    # Custom paint: border, accent lines, animated spinner dot
    $form.Add_Paint({
        param($s, $e)
        $g = $e.Graphics
        $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias

        # Outer border with purple tint
        $borderPen = New-Object System.Drawing.Pen(
            [System.Drawing.Color]::FromArgb(45, 145, 120, 225), 1
        )
        $g.DrawRectangle($borderPen, 0, 0, ($s.Width - 1), ($s.Height - 1))
        $borderPen.Dispose()

        # Top accent gradient (purple)
        try {
            $topBrush = New-Object System.Drawing.Drawing2D.LinearGradientBrush(
                (New-Object System.Drawing.Point(0, 0)),
                (New-Object System.Drawing.Point($s.Width, 0)),
                [System.Drawing.Color]::FromArgb(200, 145, 120, 225),
                [System.Drawing.Color]::FromArgb(10, 145, 120, 225)
            )
            $g.FillRectangle($topBrush, 0, 0, $s.Width, 2)
            $topBrush.Dispose()
        } catch {
            $topPen = New-Object System.Drawing.Pen(
                [System.Drawing.Color]::FromArgb(140, 145, 120, 225), 2
            )
            $g.DrawLine($topPen, 1, 0, ($s.Width - 2), 0)
            $topPen.Dispose()
        }

        # Left accent bar
        $leftBrush = New-Object System.Drawing.SolidBrush(
            [System.Drawing.Color]::FromArgb(100, 145, 120, 225)
        )
        $g.FillRectangle($leftBrush, 0, 2, 3, ($s.Height - 4))
        $leftBrush.Dispose()

        # Animated spinner dot
        $spinAngle = $script:ProgressAngle * [Math]::PI / 180.0
        $cx = 20
        $cy = 22
        $spinR = 5
        $dotX = $cx + [Math]::Cos($spinAngle) * $spinR
        $dotY = $cy + [Math]::Sin($spinAngle) * $spinR
        $dotBrush = New-Object System.Drawing.SolidBrush(
            [System.Drawing.Color]::FromArgb(255, 145, 120, 225)
        )
        $g.FillEllipse($dotBrush, ($dotX - 3), ($dotY - 3), 6, 6)
        $dotBrush.Dispose()
        # Faded trail dots
        for ($i = 1; $i -le 3; $i++) {
            $trailAngle = ($script:ProgressAngle - $i * 30) * [Math]::PI / 180.0
            $tx = $cx + [Math]::Cos($trailAngle) * $spinR
            $ty = $cy + [Math]::Sin($trailAngle) * $spinR
            $alpha = [Math]::Max(10, 160 - $i * 50)
            $trailBrush = New-Object System.Drawing.SolidBrush(
                [System.Drawing.Color]::FromArgb($alpha, 145, 120, 225)
            )
            $trailSize = [Math]::Max(2, 5 - $i)
            $g.FillEllipse($trailBrush, ($tx - $trailSize/2), ($ty - $trailSize/2), $trailSize, $trailSize)
            $trailBrush.Dispose()
        }
    })

    # Title label (gold accent)
    $titleLabel = New-Object System.Windows.Forms.Label
    $titleLabel.Text = $Title
    $titleLabel.ForeColor = [System.Drawing.Color]::FromArgb(255, 230, 190, 70)
    $titleLabel.Font = New-Object System.Drawing.Font("Segoe UI Semibold", 10.5)
    $titleLabel.Location = New-Object System.Drawing.Point(34, 10)
    $titleLabel.Size = New-Object System.Drawing.Size(330, 24)
    $titleLabel.BackColor = [System.Drawing.Color]::Transparent
    $form.Controls.Add($titleLabel)

    # Step label
    $stepLabel = New-Object System.Windows.Forms.Label
    $stepLabel.Text = $StepText
    $stepLabel.ForeColor = [System.Drawing.Color]::FromArgb(255, 160, 160, 170)
    $stepLabel.Font = New-Object System.Drawing.Font("Segoe UI", 9)
    $stepLabel.Location = New-Object System.Drawing.Point(16, 46)
    $stepLabel.Size = New-Object System.Drawing.Size(348, 20)
    $stepLabel.BackColor = [System.Drawing.Color]::Transparent
    $form.Controls.Add($stepLabel)

    # Progress bar track (dark well)
    $progressTrack = New-Object System.Windows.Forms.Panel
    $progressTrack.Location = New-Object System.Drawing.Point(16, 80)
    $progressTrack.Size = New-Object System.Drawing.Size(348, 6)
    $progressTrack.BackColor = [System.Drawing.Color]::FromArgb(255, 36, 36, 42)

    # Track paint with rounded ends
    $progressTrack.Add_Paint({
        param($s, $e)
        $g = $e.Graphics
        $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
        $brush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(255, 36, 36, 42))
        $r = 3
        $d = $r * 2
        $path = New-Object System.Drawing.Drawing2D.GraphicsPath
        $rect = New-Object System.Drawing.Rectangle(0, 0, ($s.Width - 1), ($s.Height - 1))
        $path.AddArc($rect.X, $rect.Y, $d, $d, 180, 90)
        $path.AddArc(($rect.Right - $d), $rect.Y, $d, $d, 270, 90)
        $path.AddArc(($rect.Right - $d), ($rect.Bottom - $d), $d, $d, 0, 90)
        $path.AddArc($rect.X, ($rect.Bottom - $d), $d, $d, 90, 90)
        $path.CloseFigure()
        $g.FillPath($brush, $path)
        $path.Dispose()
        $brush.Dispose()
    })

    # Progress bar fill (gradient purple with shimmer)
    $progressFill = New-Object System.Windows.Forms.Panel
    $progressFill.Location = New-Object System.Drawing.Point(0, 0)
    $progressFill.Size = New-Object System.Drawing.Size(0, 6)
    $progressFill.BackColor = [System.Drawing.Color]::Transparent
    $capturedFill = $progressFill
    $progressFill.Add_Paint({
        param($s, $e)
        if ($s.Width -le 1) { return }
        $g = $e.Graphics
        $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
        try {
            $fillBrush = New-Object System.Drawing.Drawing2D.LinearGradientBrush(
                (New-Object System.Drawing.Rectangle(0, 0, [Math]::Max(2, $s.Width), $s.Height)),
                [System.Drawing.Color]::FromArgb(255, 120, 95, 210),
                [System.Drawing.Color]::FromArgb(255, 175, 145, 240),
                [System.Drawing.Drawing2D.LinearGradientMode]::Horizontal
            )
            $g.FillRectangle($fillBrush, 0, 0, $s.Width, $s.Height)
            $fillBrush.Dispose()
        } catch {
            $fallback = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(255, 145, 120, 225))
            $g.FillRectangle($fallback, 0, 0, $s.Width, $s.Height)
            $fallback.Dispose()
        }

        # Shimmer highlight overlay
        $shimmerX = $script:ProgressShimmerOffset
        if ($shimmerX -lt $s.Width) {
            $shimmerBrush = New-Object System.Drawing.SolidBrush(
                [System.Drawing.Color]::FromArgb(50, 255, 255, 255)
            )
            $g.FillRectangle($shimmerBrush, $shimmerX, 0, [Math]::Min(60, $s.Width - $shimmerX), $s.Height)
            $shimmerBrush.Dispose()
        }
    })
    $progressTrack.Controls.Add($progressFill)
    $form.Controls.Add($progressTrack)

    # Animation timer (spinner + indeterminate progress bar + shimmer)
    $timer = New-Object System.Windows.Forms.Timer
    $script:ProgressTimer = $timer
    $timer.Interval = 50
    $script:ProgressAngle = 0
    $script:ProgressShimmerOffset = -60
    $timer.Add_Tick({
        try {
            $script:ProgressAngle = ($script:ProgressAngle + 8) % 360

            if ($script:ProgressForm -and $script:ProgressBar -and -not $script:ProgressForm.IsDisposed) {
                # Indeterminate bar: slides back and forth
                $barWidth = 100
                $maxX = 348
                $cycle = ($script:ProgressAngle * 2) % ($maxX * 2)
                $x = if ($cycle -lt $maxX) { $cycle } else { $maxX * 2 - $cycle }
                $x = [int]$x
                if (($x + $barWidth) -gt $maxX) {
                    $barWidth = $maxX - $x
                }
                $script:ProgressBar.Location = New-Object System.Drawing.Point($x, 0)
                $script:ProgressBar.Size = New-Object System.Drawing.Size([Math]::Max(1, $barWidth), 6)

                # Shimmer effect
                $script:ProgressShimmerOffset += 4
                if ($script:ProgressShimmerOffset -gt $barWidth + 60) {
                    $script:ProgressShimmerOffset = -60
                }

                $script:ProgressBar.Invalidate()
                $script:ProgressForm.Invalidate()
            }
        } catch { try { $timer.Stop() } catch {} }
    })
    $timer.Start()

    # Cancel link
    $cancelLabel = New-Object System.Windows.Forms.Label
    $cancelLabel.Text = "Cancel"
    $cancelLabel.ForeColor = [System.Drawing.Color]::FromArgb(255, 100, 100, 110)
    $cancelLabel.Font = New-Object System.Drawing.Font("Segoe UI", 8)
    $cancelLabel.Location = New-Object System.Drawing.Point(316, 106)
    $cancelLabel.Size = New-Object System.Drawing.Size(50, 20)
    $cancelLabel.BackColor = [System.Drawing.Color]::Transparent
    $cancelLabel.Cursor = [System.Windows.Forms.Cursors]::Hand
    $cancelLabel.TextAlign = [System.Drawing.ContentAlignment]::MiddleRight
    $cancelLabel.Add_MouseEnter({ $this.ForeColor = [System.Drawing.Color]::FromArgb(255, 220, 75, 75) })
    $cancelLabel.Add_MouseLeave({ $this.ForeColor = [System.Drawing.Color]::FromArgb(255, 100, 100, 110) })
    $form.Controls.Add($cancelLabel)

    # Elapsed time label
    $elapsedLabel = New-Object System.Windows.Forms.Label
    $elapsedLabel.Text = "0s"
    $elapsedLabel.ForeColor = [System.Drawing.Color]::FromArgb(255, 80, 80, 88)
    $elapsedLabel.Font = New-Object System.Drawing.Font("Consolas", 7.5)
    $elapsedLabel.Location = New-Object System.Drawing.Point(16, 108)
    $elapsedLabel.Size = New-Object System.Drawing.Size(80, 16)
    $elapsedLabel.BackColor = [System.Drawing.Color]::Transparent
    $form.Controls.Add($elapsedLabel)

    # Elapsed time updater (piggybacked on main animation timer via a secondary timer)
    $script:ProgressStartTime = Get-Date
    $elapsedTimer = New-Object System.Windows.Forms.Timer
    $elapsedTimer.Interval = 1000
    $capturedElapsed = $elapsedLabel
    $elapsedTimer.Add_Tick({
        try {
            if ($capturedElapsed -and -not $capturedElapsed.IsDisposed) {
                $seconds = [int]((Get-Date) - $script:ProgressStartTime).TotalSeconds
                $capturedElapsed.Text = "${seconds}s"
            }
        } catch { try { $elapsedTimer.Stop() } catch {} }
    })
    $elapsedTimer.Start()
    $script:ProgressElapsedTimer = $elapsedTimer

    $script:ProgressForm = $form
    $script:ProgressLabel = $stepLabel
    $script:ProgressBar = $progressFill

    $form.Show()

    # Apply DWM effects
    try {
        if ("DwmHelper" -as [type]) {
            Apply-DwmWindowEffects -Form $form -CornerStyle 3 -BorderColorRGB @(145, 120, 225)
        }
    } catch {}

    # Fade-in animation
    $fadeInTimer = New-Object System.Windows.Forms.Timer
    $fadeInTimer.Interval = 16
    $fadeInTimer.Add_Tick({
        try {
            if ($script:ProgressForm -and -not $script:ProgressForm.IsDisposed) {
                $newOp = $script:ProgressForm.Opacity + 0.12
                if ($newOp -ge 0.97) {
                    $script:ProgressForm.Opacity = 0.97
                    $fadeInTimer.Stop()
                    $fadeInTimer.Dispose()
                }
                else {
                    $script:ProgressForm.Opacity = $newOp
                }
            }
            else {
                $fadeInTimer.Stop()
                $fadeInTimer.Dispose()
            }
        } catch { try { $fadeInTimer.Stop(); $fadeInTimer.Dispose() } catch {} }
    })
    $fadeInTimer.Start()
}

function Update-ProgressOverlay {
    <#
    .SYNOPSIS
    Updates the step text in the progress overlay.
    #>
    param([string]$StepText)

    if ($script:ProgressForm -and $script:ProgressLabel -and -not $script:ProgressForm.IsDisposed) {
        $script:ProgressLabel.Text = $StepText
        $script:ProgressForm.Refresh()
    }
}

function Close-ProgressOverlay {
    <#
    .SYNOPSIS
    Closes and disposes the progress overlay and all timers.
    #>
    if ($script:ProgressElapsedTimer) {
        try { $script:ProgressElapsedTimer.Stop(); $script:ProgressElapsedTimer.Dispose() } catch {}
        $script:ProgressElapsedTimer = $null
    }
    if ($script:ProgressTimer) {
        $script:ProgressTimer.Stop()
        $script:ProgressTimer.Dispose()
        $script:ProgressTimer = $null
    }
    if ($script:ProgressForm) {
        try {
            $script:ProgressForm.Hide()
            [System.Windows.Forms.Application]::DoEvents()
            $script:ProgressForm.Close()
            $script:ProgressForm.Dispose()
        } catch {
            if (Get-Command Write-TrayLog -ErrorAction SilentlyContinue) {
                Write-TrayLog "ProgressForm disposal error: $($_.Exception.Message)" -Level "WARN"
            }
        }
        $script:ProgressForm = $null
    }
    $script:ProgressLabel = $null
    $script:ProgressBar = $null
}

# ============================================================================
# TOAST NOTIFICATIONS (Legacy-compatible wrapper)
# ============================================================================

function Show-ABSONotification {
    <#
    .SYNOPSIS
    Shows a themed toast notification (v2.0). Legacy-compatible signature.
    .PARAMETER Title
    Notification title.
    .PARAMETER Message
    Notification message body.
    .PARAMETER Type
    One of: Info, Warning, Error, Success
    .PARAMETER NotifyIcon
    The NotifyIcon instance (used to update tooltip text).
    .PARAMETER Duration
    Duration in milliseconds (default 4000).
    #>
    param(
        [string]$Title,
        [string]$Message,
        [ValidateSet("Info", "Warning", "Error", "Success")]
        [string]$Type = "Info",
        [System.Windows.Forms.NotifyIcon]$NotifyIcon,
        [int]$Duration = 4000
    )

    # Update tooltip text on the tray icon
    if ($NotifyIcon) {
        $maxLen = [Math]::Min(63, "$Title - $Message".Length)
        $NotifyIcon.Text = "$Title - $Message".Substring(0, $maxLen)
    }

    Show-ThemedToast -Title $Title -Message $Message -Type $Type -Duration $Duration
}

# ============================================================================
# STATUS BAR
# ============================================================================

function New-StatusBarItem {
    <#
    .SYNOPSIS
    Creates a status bar menu item showing last action, current game, etc.
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
