# ABSO-QuickPanel.ps1 - Floating quick-access panel for A.B.S.O. tray
# Always-on-top mini panel with favorite profile buttons

$script:QuickPanelForm = $null
$script:QuickPanelVisible = $false

function Blend-QPColor {
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

function Show-QuickPanel {
    <#
    .SYNOPSIS
    Shows the floating quick panel with favorite profile buttons.
    .PARAMETER Favorites
    Array of profile IDs that are favorited.
    .PARAMETER Profiles
    The full profiles hashtable.
    .PARAMETER ActiveProfile
    Currently active profile ID (or $null).
    .PARAMETER OnApply
    Scriptblock to call when a profile button is clicked. Receives profile ID.
    #>
    param(
        [string[]]$Favorites,
        [System.Collections.Specialized.OrderedDictionary]$Profiles,
        [string]$ActiveProfile,
        [scriptblock]$OnApply
    )

    if ($script:QuickPanelForm -and -not $script:QuickPanelForm.IsDisposed) {
        try {
            $script:QuickPanelForm.Hide()
            [System.Windows.Forms.Application]::DoEvents()
            $script:QuickPanelForm.Close()
            $script:QuickPanelForm.Dispose()
        } catch {
            Write-TrayLog "QuickPanel disposal error: $($_.Exception.Message)" -Level "WARN"
        }
        $script:QuickPanelForm = $null
    }

    $favProfiles = @()
    foreach ($fav in $Favorites) {
        if ($Profiles.Contains($fav)) {
            $favProfiles += @{ Id = $fav; Profile = $Profiles[$fav] }
        }
    }

    # Take top 3 favorites
    if ($favProfiles.Count -gt 3) {
        $favProfiles = $favProfiles[0..2]
    }

    if ($favProfiles.Count -eq 0) { return }

    $btnHeight = 44
    $padding = 10
    $panelWidth = 240
    $panelHeight = $padding + ($favProfiles.Count * ($btnHeight + 5)) + $padding + 28  # +28 for header

    $form = New-Object System.Windows.Forms.Form
    $form.Text = ""
    $form.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::None
    $form.BackColor = [System.Drawing.Color]::FromArgb(255, 24, 24, 28)
    $form.Size = New-Object System.Drawing.Size($panelWidth, $panelHeight)
    $form.StartPosition = [System.Windows.Forms.FormStartPosition]::Manual
    $form.TopMost = $true
    $form.ShowInTaskbar = $false
    $form.Opacity = 0.94

    # Position bottom-right
    $screen = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
    $form.Location = New-Object System.Drawing.Point(
        ($screen.Right - $panelWidth - 16),
        ($screen.Bottom - $panelHeight - 16)
    )

    # Enable dragging
    $script:QP_Dragging = $false
    $script:QP_DragStart = [System.Drawing.Point]::Empty
    $form.Add_MouseDown({
        param($s, $e)
        if ($e.Button -eq [System.Windows.Forms.MouseButtons]::Left) {
            $script:QP_Dragging = $true
            $script:QP_DragStart = $e.Location
        }
    })
    $form.Add_MouseMove({
        param($s, $e)
        if ($script:QP_Dragging) {
            $newX = $s.Location.X + $e.X - $script:QP_DragStart.X
            $newY = $s.Location.Y + $e.Y - $script:QP_DragStart.Y
            # Clamp to screen bounds so the panel can't be dragged off-screen
            $screen = [System.Windows.Forms.Screen]::FromControl($s).WorkingArea
            $newX = [Math]::Max($screen.Left, [Math]::Min($newX, $screen.Right - $s.Width))
            $newY = [Math]::Max($screen.Top, [Math]::Min($newY, $screen.Bottom - $s.Height))
            $s.Location = New-Object System.Drawing.Point($newX, $newY)
        }
    })
    $form.Add_MouseUp({ $script:QP_Dragging = $false })

    # Border paint with gradient top accent
    $form.Add_Paint({
        param($s, $e)
        $g = $e.Graphics
        $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
        # Outer border
        $borderPen = New-Object System.Drawing.Pen(
            [System.Drawing.Color]::FromArgb(50, 220, 180, 70), 1
        )
        $g.DrawRectangle($borderPen, 0, 0, ($s.Width - 1), ($s.Height - 1))
        $borderPen.Dispose()
        # Top accent line (gold gradient)
        $topPen = New-Object System.Drawing.Pen(
            [System.Drawing.Color]::FromArgb(120, 230, 190, 70), 2
        )
        $g.DrawLine($topPen, 1, 0, ($s.Width - 2), 0)
        $topPen.Dispose()
        # Header background gradient
        $headerBrush = New-Object System.Drawing.SolidBrush(
            [System.Drawing.Color]::FromArgb(255, 20, 20, 24)
        )
        $g.FillRectangle($headerBrush, 1, 1, ($s.Width - 2), 26)
        $headerBrush.Dispose()
    })

    # Header
    $headerLabel = New-Object System.Windows.Forms.Label
    $headerLabel.Text = "A.B.S.O."
    $headerLabel.ForeColor = [System.Drawing.Color]::FromArgb(255, 220, 180, 70)
    $headerLabel.Font = New-Object System.Drawing.Font("Segoe UI", 8, [System.Drawing.FontStyle]::Bold)
    $headerLabel.Location = New-Object System.Drawing.Point($padding, $padding)
    $headerLabel.AutoSize = $true
    $headerLabel.BackColor = [System.Drawing.Color]::Transparent
    $form.Controls.Add($headerLabel)

    # Close button
    $closeLabel = New-Object System.Windows.Forms.Label
    $closeLabel.Text = "X"
    $closeLabel.ForeColor = [System.Drawing.Color]::FromArgb(255, 100, 100, 100)
    $closeLabel.Font = New-Object System.Drawing.Font("Segoe UI", 8, [System.Drawing.FontStyle]::Bold)
    $closeLabel.Location = New-Object System.Drawing.Point(($panelWidth - 20), $padding)
    $closeLabel.Size = New-Object System.Drawing.Size(14, 16)
    $closeLabel.BackColor = [System.Drawing.Color]::Transparent
    $closeLabel.Cursor = [System.Windows.Forms.Cursors]::Hand
    $closeLabel.TextAlign = [System.Drawing.ContentAlignment]::MiddleCenter
    $closeLabel.Add_Click({
        Close-QuickPanel
    })
    $closeLabel.Add_MouseEnter({ $this.ForeColor = [System.Drawing.Color]::FromArgb(255, 220, 70, 70) })
    $closeLabel.Add_MouseLeave({ $this.ForeColor = [System.Drawing.Color]::FromArgb(255, 100, 100, 100) })
    $form.Controls.Add($closeLabel)

    # Profile buttons with sub-text
    $y = $padding + 28
    foreach ($entry in $favProfiles) {
        $catColor = $null
        $catName = $entry.Profile.Cat
        if (Get-Command Get-CategoryColor -ErrorAction SilentlyContinue) {
            $catColor = Get-CategoryColor -Category $catName -Fallback ([System.Drawing.Color]::FromArgb(255, 200, 200, 200))
        }
        else {
            $catColor = [System.Drawing.Color]::FromArgb(255, 200, 200, 200)
        }

        $isActive = ($entry.Id -eq $ActiveProfile)

        # Container panel for custom two-line button
        $btnPanel = New-Object System.Windows.Forms.Panel
        $btnPanel.Tag = $entry.Id
        $btnPanel.Location = New-Object System.Drawing.Point($padding, $y)
        $btnPanel.Size = New-Object System.Drawing.Size(($panelWidth - $padding * 2), $btnHeight)
        $btnPanel.Cursor = [System.Windows.Forms.Cursors]::Hand

        if ($isActive) {
            $btnPanel.BackColor = Blend-QPColor -Base ([System.Drawing.Color]::FromArgb(255, 24, 24, 28)) -Overlay $catColor -Ratio 0.20
        }
        else {
            $btnPanel.BackColor = Blend-QPColor -Base ([System.Drawing.Color]::FromArgb(255, 38, 38, 44)) -Overlay $catColor -Ratio 0.08
        }

        # Custom paint for border + left accent bar
        $capturedCatColor = $catColor
        $capturedIsActive = $isActive
        $btnPanel.Add_Paint({
            param($s, $e)
            $g = $e.Graphics
            $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
            # Border
            $borderAlpha = if ($capturedIsActive) { 100 } else { 40 }
            $borderPen = New-Object System.Drawing.Pen(
                [System.Drawing.Color]::FromArgb($borderAlpha, $capturedCatColor.R, $capturedCatColor.G, $capturedCatColor.B), 1
            )
            $g.DrawRectangle($borderPen, 0, 0, ($s.Width - 1), ($s.Height - 1))
            $borderPen.Dispose()
            # Left accent bar
            $barAlpha = if ($capturedIsActive) { 220 } else { 80 }
            $barBrush = New-Object System.Drawing.SolidBrush(
                [System.Drawing.Color]::FromArgb($barAlpha, $capturedCatColor.R, $capturedCatColor.G, $capturedCatColor.B)
            )
            $g.FillRectangle($barBrush, 0, 2, 3, ($s.Height - 4))
            $barBrush.Dispose()
            # Active glow indicator
            if ($capturedIsActive) {
                $glowBrush = New-Object System.Drawing.SolidBrush(
                    [System.Drawing.Color]::FromArgb(20, $capturedCatColor.R, $capturedCatColor.G, $capturedCatColor.B)
                )
                $g.FillRectangle($glowBrush, 0, 0, $s.Width, $s.Height)
                $glowBrush.Dispose()
            }
        }.GetNewClosure())

        # Profile name label
        $nameLabel = New-Object System.Windows.Forms.Label
        $nameLabel.Text = $entry.Profile.Name
        $nameLabel.Location = New-Object System.Drawing.Point(10, 4)
        $nameLabel.Size = New-Object System.Drawing.Size(($panelWidth - $padding * 2 - 16), 18)
        $nameLabel.ForeColor = if ($isActive) {
            [System.Drawing.Color]::FromArgb(255,
                [Math]::Min(255, $catColor.R + 30),
                [Math]::Min(255, $catColor.G + 30),
                [Math]::Min(255, $catColor.B + 30)
            )
        } else { $catColor }
        $nameLabel.Font = if ($isActive) {
            New-Object System.Drawing.Font("Segoe UI", 8.5, [System.Drawing.FontStyle]::Bold)
        } else {
            New-Object System.Drawing.Font("Segoe UI", 8.5)
        }
        $nameLabel.BackColor = [System.Drawing.Color]::Transparent
        $nameLabel.Cursor = [System.Windows.Forms.Cursors]::Hand
        $btnPanel.Controls.Add($nameLabel)

        # Sub-text label (profile settings summary)
        $subLabel = New-Object System.Windows.Forms.Label
        $subText = if ($entry.Profile.Sub) { $entry.Profile.Sub } else { $entry.Profile.Cat }
        $subLabel.Text = $subText
        $subLabel.Location = New-Object System.Drawing.Point(10, 22)
        $subLabel.Size = New-Object System.Drawing.Size(($panelWidth - $padding * 2 - 16), 16)
        $subLabel.ForeColor = [System.Drawing.Color]::FromArgb(160, $catColor.R, $catColor.G, $catColor.B)
        $subLabel.Font = New-Object System.Drawing.Font("Segoe UI", 7)
        $subLabel.BackColor = [System.Drawing.Color]::Transparent
        $subLabel.Cursor = [System.Windows.Forms.Cursors]::Hand
        $btnPanel.Controls.Add($subLabel)

        # Hover effects for the panel
        $hoverColor = Blend-QPColor -Base $btnPanel.BackColor -Overlay $catColor -Ratio 0.15
        $normalColor = $btnPanel.BackColor
        $capturedHoverColor = $hoverColor
        $capturedNormalColor = $normalColor
        $hoverAction = { $this.Parent.BackColor = $capturedHoverColor }.GetNewClosure()
        $leaveAction = { $this.Parent.BackColor = $capturedNormalColor }.GetNewClosure()
        $panelHoverAction = { $this.BackColor = $capturedHoverColor }.GetNewClosure()
        $panelLeaveAction = { $this.BackColor = $capturedNormalColor }.GetNewClosure()

        $nameLabel.Add_MouseEnter($hoverAction)
        $nameLabel.Add_MouseLeave($leaveAction)
        $subLabel.Add_MouseEnter($hoverAction)
        $subLabel.Add_MouseLeave($leaveAction)
        $btnPanel.Add_MouseEnter($panelHoverAction)
        $btnPanel.Add_MouseLeave($panelLeaveAction)

        # Click handlers
        $capturedId = $entry.Id
        $clickAction = {
            if ($OnApply) { & $OnApply $capturedId }
        }.GetNewClosure()
        $btnPanel.Add_Click($clickAction)
        $nameLabel.Add_Click($clickAction)
        $subLabel.Add_Click($clickAction)

        $form.Controls.Add($btnPanel)
        $y += $btnHeight + 5
    }

    $script:QuickPanelForm = $form
    $script:QuickPanelVisible = $true
    $form.Show()
}

function Close-QuickPanel {
    <#
    .SYNOPSIS
    Closes the quick panel if it's open.
    #>
    if ($script:QuickPanelForm -and -not $script:QuickPanelForm.IsDisposed) {
        try {
            $script:QuickPanelForm.Hide()  # Force desktop repaint before disposing
            [System.Windows.Forms.Application]::DoEvents()
            $script:QuickPanelForm.Close()
            $script:QuickPanelForm.Dispose()
        } catch {
            Write-TrayLog "QuickPanel Close disposal error: $($_.Exception.Message)" -Level "WARN"
        }
        $script:QuickPanelForm = $null
    }
    $script:QuickPanelVisible = $false
}

function Update-QuickPanel {
    <#
    .SYNOPSIS
    Refreshes the quick panel with current state. Call after profile changes.
    #>
    param(
        [string[]]$Favorites,
        [System.Collections.Specialized.OrderedDictionary]$Profiles,
        [string]$ActiveProfile,
        [scriptblock]$OnApply
    )

    if ($script:QuickPanelVisible) {
        Show-QuickPanel -Favorites $Favorites -Profiles $Profiles -ActiveProfile $ActiveProfile -OnApply $OnApply
    }
}
