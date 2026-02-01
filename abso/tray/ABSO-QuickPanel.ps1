# ABSO-QuickPanel.ps1 - Floating quick-access panel for A.B.S.O. tray
# Always-on-top mini panel with favorite profile buttons

$script:QuickPanelForm = $null
$script:QuickPanelVisible = $false

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
            $script:QuickPanelForm.Close()
            $script:QuickPanelForm.Dispose()
        } catch {}
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

    $btnHeight = 32
    $padding = 8
    $panelWidth = 200
    $panelHeight = $padding + ($favProfiles.Count * ($btnHeight + 4)) + $padding + 24  # +24 for header

    $form = New-Object System.Windows.Forms.Form
    $form.Text = ""
    $form.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::None
    $form.BackColor = [System.Drawing.Color]::FromArgb(255, 28, 28, 32)
    $form.Size = New-Object System.Drawing.Size($panelWidth, $panelHeight)
    $form.StartPosition = [System.Windows.Forms.FormStartPosition]::Manual
    $form.TopMost = $true
    $form.ShowInTaskbar = $false
    $form.Opacity = 0.92

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

    # Border paint
    $form.Add_Paint({
        param($s, $e)
        $pen = New-Object System.Drawing.Pen(
            [System.Drawing.Color]::FromArgb(60, 220, 180, 70), 1
        )
        $e.Graphics.DrawRectangle($pen, 0, 0, ($s.Width - 1), ($s.Height - 1))
        $pen.Dispose()
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

    # Profile buttons
    $y = $padding + 24
    foreach ($entry in $favProfiles) {
        $btn = New-Object System.Windows.Forms.Button
        $btn.Text = $entry.Profile.Name
        $btn.Tag = $entry.Id
        $btn.Location = New-Object System.Drawing.Point($padding, $y)
        $btn.Size = New-Object System.Drawing.Size(($panelWidth - $padding * 2), $btnHeight)
        $btn.FlatStyle = [System.Windows.Forms.FlatStyle]::Flat
        $btn.Font = New-Object System.Drawing.Font("Segoe UI", 8.5)
        $btn.Cursor = [System.Windows.Forms.Cursors]::Hand
        $btn.TextAlign = [System.Drawing.ContentAlignment]::MiddleLeft
        $btn.Padding = New-Object System.Windows.Forms.Padding(8, 0, 0, 0)

        if ($entry.Id -eq $ActiveProfile) {
            $btn.BackColor = [System.Drawing.Color]::FromArgb(255, 40, 80, 50)
            $btn.ForeColor = [System.Drawing.Color]::FromArgb(255, 90, 200, 120)
            $btn.FlatAppearance.BorderColor = [System.Drawing.Color]::FromArgb(255, 60, 120, 70)
        }
        else {
            $btn.BackColor = [System.Drawing.Color]::FromArgb(255, 45, 45, 50)
            $btn.ForeColor = [System.Drawing.Color]::FromArgb(255, 200, 200, 200)
            $btn.FlatAppearance.BorderColor = [System.Drawing.Color]::FromArgb(255, 60, 60, 65)
        }

        $btn.FlatAppearance.MouseOverBackColor = [System.Drawing.Color]::FromArgb(255, 60, 60, 68)
        $btn.FlatAppearance.BorderSize = 1

        $capturedId = $entry.Id
        $btn.Add_Click({
            if ($OnApply) { & $OnApply $capturedId }
        }.GetNewClosure())

        $form.Controls.Add($btn)
        $y += $btnHeight + 4
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
            $script:QuickPanelForm.Close()
            $script:QuickPanelForm.Dispose()
        } catch {}
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
