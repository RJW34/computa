# ABSO-QuickPanel.ps1 - v3.0 "Phosphor" retro-gaming HUD quick-launch panel
#
# Tron / retro-arcade HUD aesthetic to match ABSO-Notifications.ps1 v5.0.
# Phosphor cyan accent, Bahnschrift Condensed headlines, Cascadia Code body,
# CRT scanlines, L-shaped corner brackets, solid Ink-100 label backgrounds
# (no transparency races).

$script:QuickPanelForm    = $null
$script:QuickPanelVisible = $false

# ============================================================================
# PHOSPHOR PALETTE (mirrors $script:Penumbra in ABSO-Notifications.ps1)
# ============================================================================
$script:QPPalette = @{
    Ink100   = [System.Drawing.Color]::FromArgb(255, 14, 18, 26)
    Ink150   = [System.Drawing.Color]::FromArgb(255, 17, 21, 31)
    Ink200   = [System.Drawing.Color]::FromArgb(255, 19, 24, 36)
    Ink300   = [System.Drawing.Color]::FromArgb(255, 27, 34, 48)
    Paper    = [System.Drawing.Color]::FromArgb(255, 232, 234, 240)
    Mist     = [System.Drawing.Color]::FromArgb(255, 150, 168, 180)
    Fog      = [System.Drawing.Color]::FromArgb(255, 95, 115, 130)
    Lagoon   = [System.Drawing.Color]::FromArgb(255, 0, 245, 212)   # phosphor cyan
    Rule     = [System.Drawing.Color]::FromArgb(70, 0, 245, 212)
    Scanline = [System.Drawing.Color]::FromArgb(6, 255, 255, 255)
}

$script:QPFont_Eyebrow = $null
$script:QPFont_Title   = $null
$script:QPFont_Sub     = $null

function _QP-Resolve-Font {
    param([string[]]$Families, [float]$Size, [System.Drawing.FontStyle]$Style = [System.Drawing.FontStyle]::Regular)
    foreach ($family in $Families) {
        try {
            $f = New-Object System.Drawing.Font($family, $Size, $Style)
            if ($f.FontFamily.Name -ieq $family) { return $f }
            $root = ($family -split ' ')[0]
            if ($f.FontFamily.Name -ilike "$root*") { return $f }
            $f.Dispose()
        } catch {}
    }
    return New-Object System.Drawing.Font("Segoe UI", $Size, $Style)
}

function _QP-Ensure-Fonts {
    if ($null -ne $script:QPFont_Title) { return }
    # Bahnschrift SemiBold Condensed for the eyebrow tag (geometric HUD caps).
    $script:QPFont_Eyebrow = _QP-Resolve-Font `
        -Families @("Bahnschrift SemiBold Condensed","Bahnschrift Condensed","Bahnschrift","Segoe UI Semibold") `
        -Size 7.5 -Style ([System.Drawing.FontStyle]::Bold)
    # Bahnschrift SemiBold Condensed headline for profile names - matches the
    # toast Title font family for visual continuity across the two surfaces.
    $script:QPFont_Title   = _QP-Resolve-Font `
        -Families @("Bahnschrift SemiBold Condensed","Bahnschrift Condensed","Bahnschrift","Segoe UI Semibold") `
        -Size 11.5 -Style ([System.Drawing.FontStyle]::Bold)
    # Cascadia Code for the sub-text - developer mono with slashed zero.
    $script:QPFont_Sub     = _QP-Resolve-Font `
        -Families @("Cascadia Code","Cascadia Mono","Consolas") `
        -Size 8.0 -Style ([System.Drawing.FontStyle]::Regular)
}

# ============================================================================
# IMAGE CLEANUP
# ============================================================================

function Clear-QuickPanelGeneratedImages {
    param([System.Windows.Forms.Control]$Root)
    if (-not $Root) { return }
    foreach ($child in @($Root.Controls)) {
        Clear-QuickPanelGeneratedImages -Root $child
    }
    if ($Root -is [System.Windows.Forms.PictureBox]) {
        $image = $Root.Image
        if ($image) {
            $Root.Image = $null
            try { $image.Dispose() } catch {}
        }
    }
}

# ============================================================================
# PUBLIC: Show-QuickPanel
# ============================================================================

function Show-QuickPanel {
    <#
    .SYNOPSIS
    Phosphor HUD card-stack of favorite profiles, always-on-top, draggable.

    .PARAMETER Favorites    Array of profile IDs that are favorited.
    .PARAMETER Profiles     The full profiles hashtable.
    .PARAMETER ActiveProfile Currently active profile ID (or $null).
    .PARAMETER OnApply      Scriptblock to call when a card is clicked. Receives profile ID.
    #>
    param(
        [string[]]$Favorites,
        [System.Collections.Specialized.OrderedDictionary]$Profiles,
        [string]$ActiveProfile,
        [scriptblock]$OnApply
    )

    _QP-Ensure-Fonts

    if ($script:QuickPanelForm -and -not $script:QuickPanelForm.IsDisposed) {
        try {
            Clear-QuickPanelGeneratedImages -Root $script:QuickPanelForm
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
    if ($favProfiles.Count -gt 3) { $favProfiles = $favProfiles[0..2] }
    if ($favProfiles.Count -eq 0) { return }

    # Phosphor HUD card dimensions
    $panelWidth   = 280
    $cardHeight   = 56
    $cardGap      = 6
    $padX         = 18
    $padTop       = 14
    $headerHeight = 38
    $padBottom    = 14
    $panelHeight  = $padTop + $headerHeight + ($favProfiles.Count * ($cardHeight + $cardGap)) - $cardGap + $padBottom

    $form = New-Object System.Windows.Forms.Form
    $form.Text             = ""
    $form.FormBorderStyle  = [System.Windows.Forms.FormBorderStyle]::None
    $form.BackColor        = $script:QPPalette.Ink100
    $form.Size             = New-Object System.Drawing.Size($panelWidth, $panelHeight)
    $form.StartPosition    = [System.Windows.Forms.FormStartPosition]::Manual
    $form.TopMost          = $true
    $form.ShowInTaskbar    = $false
    $form.Opacity          = 0

    $screen = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
    $form.Location = New-Object System.Drawing.Point(
        ($screen.Right - $panelWidth - 18),
        ($screen.Bottom - $panelHeight - 18)
    )

    # Drag support
    $script:QP_Dragging  = $false
    $script:QP_DragStart = [System.Drawing.Point]::Empty
    $form.Add_MouseDown({
        param($s, $e)
        if ($e.Button -eq [System.Windows.Forms.MouseButtons]::Left) {
            $script:QP_Dragging  = $true
            $script:QP_DragStart = $e.Location
        }
    })
    $form.Add_MouseMove({
        param($s, $e)
        if ($script:QP_Dragging) {
            $newX = $s.Location.X + $e.X - $script:QP_DragStart.X
            $newY = $s.Location.Y + $e.Y - $script:QP_DragStart.Y
            $screen = [System.Windows.Forms.Screen]::FromControl($s).WorkingArea
            $newX = [Math]::Max($screen.Left, [Math]::Min($newX, $screen.Right - $s.Width))
            $newY = [Math]::Max($screen.Top, [Math]::Min($newY, $screen.Bottom - $s.Height))
            $s.Location = New-Object System.Drawing.Point($newX, $newY)
        }
    })
    $form.Add_MouseUp({ $script:QP_Dragging = $false })

    # Panel surface paint: solid Ink-100, CRT scanlines, L-corner brackets,
    # outline, left phosphor rail, hairline rule under the header.
    $capW = $panelWidth
    $capH = $panelHeight
    $form.Add_Paint({
        param($s, $e)
        $g = $e.Graphics
        $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
        $g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::ClearTypeGridFit

        # 1) Solid Ink-100 base (matches Form.BackColor and label backgrounds
        #    so labels composite invisibly into the surface)
        $baseBrush = New-Object System.Drawing.SolidBrush($script:QPPalette.Ink100)
        $g.FillRectangle($baseBrush, 0, 0, $capW, $capH)
        $baseBrush.Dispose()

        # 2) CRT scanlines - 1px horizontal stripes every 3px
        $scanBrush = New-Object System.Drawing.SolidBrush($script:QPPalette.Scanline)
        for ($sy = 0; $sy -lt $capH; $sy += 3) {
            $g.FillRectangle($scanBrush, 0, $sy, $capW, 1)
        }
        $scanBrush.Dispose()

        # 3) Outline (full panel hairline in phosphor cyan at low alpha)
        $outlinePen = New-Object System.Drawing.Pen(
            [System.Drawing.Color]::FromArgb(80, $script:QPPalette.Lagoon.R, $script:QPPalette.Lagoon.G, $script:QPPalette.Lagoon.B), 1
        )
        $g.DrawRectangle($outlinePen, 0, 0, ($capW - 1), ($capH - 1))
        $outlinePen.Dispose()

        # 4) Left accent rail - 6px solid phosphor + 1px feather
        $strokeBrush = New-Object System.Drawing.SolidBrush($script:QPPalette.Lagoon)
        $g.FillRectangle($strokeBrush, 0, 0, 6, $capH)
        $strokeBrush.Dispose()
        $featherBrush = New-Object System.Drawing.SolidBrush(
            [System.Drawing.Color]::FromArgb(80, $script:QPPalette.Lagoon.R, $script:QPPalette.Lagoon.G, $script:QPPalette.Lagoon.B)
        )
        $g.FillRectangle($featherBrush, 6, 0, 1, $capH)
        $featherBrush.Dispose()
        # Tick perforations every 22px - dark notches across the rail
        $tickBrush = New-Object System.Drawing.SolidBrush($script:QPPalette.Ink100)
        for ($ty = 14; $ty -lt ($capH - 6); $ty += 22) {
            $g.FillRectangle($tickBrush, 0, $ty, 6, 1)
        }
        $tickBrush.Dispose()

        # 5) L-shaped corner brackets in phosphor cyan (10px arms, 1.6px pen)
        $bracketLen = 10
        $bracketPen = New-Object System.Drawing.Pen($script:QPPalette.Lagoon, 1.6)
        # Top-right: |_ shape
        $bracketPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Flat
        $bracketPen.EndCap   = [System.Drawing.Drawing2D.LineCap]::Flat
        $g.DrawLine($bracketPen, ($capW - $bracketLen - 2), 2, ($capW - 2), 2)
        $g.DrawLine($bracketPen, ($capW - 2), 2, ($capW - 2), ($bracketLen + 2))
        # Bottom-right: ^| shape
        $g.DrawLine($bracketPen, ($capW - 2), ($capH - $bracketLen - 2), ($capW - 2), ($capH - 2))
        $g.DrawLine($bracketPen, ($capW - $bracketLen - 2), ($capH - 2), ($capW - 2), ($capH - 2))
        # Bottom-left horizontal arm (vertical is the accent rail itself)
        $g.DrawLine($bracketPen, 6, ($capH - 2), ($bracketLen + 6), ($capH - 2))
        $bracketPen.Dispose()

        # 6) Header hairline rule beneath the eyebrow heading
        $rulePen = New-Object System.Drawing.Pen($script:QPPalette.Ink300, 1)
        $g.DrawLine($rulePen, $padX, ($padTop + $headerHeight - 4),
            ($capW - $padX), ($padTop + $headerHeight - 4))
        $rulePen.Dispose()
    }.GetNewClosure())

    # Header eyebrow ("FAVORITES / QUICK LAUNCH"). Solid Ink-100 BackColor on
    # every label avoids the WinForms transparency race that produced solid
    # rectangles when Discord popped over the toast surface.
    $eyebrow = New-Object System.Windows.Forms.Label
    $eyebrow.Text      = "FAVORITES / QUICK LAUNCH"
    $eyebrow.Font      = $script:QPFont_Eyebrow
    $eyebrow.ForeColor = $script:QPPalette.Lagoon
    $eyebrow.BackColor = $script:QPPalette.Ink100
    $eyebrow.Location  = New-Object System.Drawing.Point($padX, $padTop)
    $eyebrow.Size      = New-Object System.Drawing.Size(($panelWidth - $padX * 2 - 24), 14)
    $form.Controls.Add($eyebrow)

    # Close affordance - phosphor cyan X (replaces the v2 gold/coral pair)
    $closeLabel = New-Object System.Windows.Forms.Label
    $closeLabel.Text      = [string][char]0x00D7
    $closeLabel.ForeColor = $script:QPPalette.Lagoon
    $closeLabel.Font      = New-Object System.Drawing.Font("Segoe UI", 11)
    $closeLabel.Location  = New-Object System.Drawing.Point(($panelWidth - $padX - 14), ($padTop - 4))
    $closeLabel.Size      = New-Object System.Drawing.Size(16, 18)
    $closeLabel.BackColor = $script:QPPalette.Ink100
    $closeLabel.Cursor    = [System.Windows.Forms.Cursors]::Hand
    $closeLabel.TextAlign = [System.Drawing.ContentAlignment]::MiddleCenter
    $closeLabel.Add_Click({ Close-QuickPanel })
    $closeLabel.Add_MouseEnter({ $this.ForeColor = $script:QPPalette.Paper })
    $closeLabel.Add_MouseLeave({ $this.ForeColor = $script:QPPalette.Lagoon })
    $form.Controls.Add($closeLabel)

    # Profile cards
    $y = $padTop + $headerHeight
    foreach ($entry in $favProfiles) {
        $catName = $entry.Profile.Cat
        $catColor = if (Get-Command Get-CategoryColor -ErrorAction SilentlyContinue) {
            Get-CategoryColor -Category $catName -Fallback $script:QPPalette.Lagoon
        } else { $script:QPPalette.Lagoon }
        $isActive = ($entry.Id -eq $ActiveProfile)

        $card = New-Object System.Windows.Forms.Panel
        $card.Tag      = $entry.Id
        $card.Location = New-Object System.Drawing.Point($padX, $y)
        $card.Size     = New-Object System.Drawing.Size(($panelWidth - $padX * 2), $cardHeight)
        $card.Cursor   = [System.Windows.Forms.Cursors]::Hand
        $card.BackColor = if ($isActive) { $script:QPPalette.Ink300 } else { $script:QPPalette.Ink200 }

        $capCardColor = $catColor
        $capCardActive = $isActive
        $card.Add_Paint({
            param($s, $e)
            $g = $e.Graphics
            $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias

            # 3px left accent stroke - active = full saturation, inactive = subtle
            $barAlpha = if ($capCardActive) { 220 } else { 80 }
            $bar = New-Object System.Drawing.SolidBrush(
                [System.Drawing.Color]::FromArgb($barAlpha, $capCardColor.R, $capCardColor.G, $capCardColor.B)
            )
            $g.FillRectangle($bar, 0, 0, 3, $s.Height)
            $bar.Dispose()

            # Top-right indicator pip - 2x2 phosphor-cyan dot
            $pipBrush = New-Object System.Drawing.SolidBrush($script:QPPalette.Lagoon)
            $g.FillRectangle($pipBrush, ($s.Width - 5), 3, 2, 2)
            $pipBrush.Dispose()

            # Bottom hairline rule
            $rulePen = New-Object System.Drawing.Pen(
                [System.Drawing.Color]::FromArgb(50, 255, 255, 255), 1
            )
            $g.DrawLine($rulePen, 12, ($s.Height - 1), ($s.Width - 8), ($s.Height - 1))
            $rulePen.Dispose()

            # Active indicator dot, right side
            if ($capCardActive) {
                $dotGlow = New-Object System.Drawing.SolidBrush(
                    [System.Drawing.Color]::FromArgb(50, $capCardColor.R, $capCardColor.G, $capCardColor.B)
                )
                $g.FillEllipse($dotGlow, ($s.Width - 22), (($s.Height / 2) - 6), 12, 12)
                $dotGlow.Dispose()
                $dotBrush = New-Object System.Drawing.SolidBrush($capCardColor)
                $g.FillEllipse($dotBrush, ($s.Width - 19), (($s.Height / 2) - 3), 6, 6)
                $dotBrush.Dispose()
            }
        }.GetNewClosure())

        # Icon medallion (category/game bitmap, 20x20 centered vertically).
        # Card background colors (Ink-200/Ink-300) are used for the picture
        # box BackColor so the icon composites cleanly onto the card surface.
        $cardBg = $card.BackColor
        $iconBox = New-Object System.Windows.Forms.PictureBox
        $iconBox.Location = New-Object System.Drawing.Point(14, (($cardHeight / 2) - 10))
        $iconBox.Size = New-Object System.Drawing.Size(20, 20)
        $iconBox.SizeMode = [System.Windows.Forms.PictureBoxSizeMode]::Zoom
        $iconBox.BackColor = $cardBg
        $iconBox.Cursor = [System.Windows.Forms.Cursors]::Hand
        if (Get-Command New-CategoryBitmap -ErrorAction SilentlyContinue) {
            $iconBox.Image = New-CategoryBitmap -Category $catName -Color $catColor
        }
        $card.Controls.Add($iconBox)

        # Profile name (Bahnschrift SemiBold Condensed HUD headline, paper)
        $nameLabel = New-Object System.Windows.Forms.Label
        $nameLabel.Text      = $entry.Profile.Name
        $nameLabel.Location  = New-Object System.Drawing.Point(42, 8)
        $nameLabel.Size      = New-Object System.Drawing.Size(($panelWidth - $padX * 2 - 70), 20)
        $nameLabel.ForeColor = $script:QPPalette.Paper
        $nameLabel.Font      = $script:QPFont_Title
        $nameLabel.BackColor = $cardBg
        $nameLabel.Cursor    = [System.Windows.Forms.Cursors]::Hand
        $nameLabel.AutoEllipsis = $true
        $card.Controls.Add($nameLabel)

        # Sub-text (Cascadia Code mist) - profile descriptor
        $subText = if ($entry.Profile.Sub) { $entry.Profile.Sub } else { $entry.Profile.Cat }
        $subLabel = New-Object System.Windows.Forms.Label
        $subLabel.Text      = $subText
        $subLabel.Location  = New-Object System.Drawing.Point(42, 30)
        $subLabel.Size      = New-Object System.Drawing.Size(($panelWidth - $padX * 2 - 70), 16)
        $subLabel.ForeColor = $script:QPPalette.Mist
        $subLabel.Font      = $script:QPFont_Sub
        $subLabel.BackColor = $cardBg
        $subLabel.Cursor    = [System.Windows.Forms.Cursors]::Hand
        $subLabel.AutoEllipsis = $true
        $card.Controls.Add($subLabel)

        # Hover lift: inactive Ink-200 -> Ink-300, active Ink-300 -> Ink-150-mix.
        # Update label/icon BackColors too so they stay flush with the card.
        $normalBg = $card.BackColor
        $hoverBg  = if ($isActive) {
            [System.Drawing.Color]::FromArgb(255, 38, 48, 66)
        } else {
            $script:QPPalette.Ink300
        }
        $capCard = $card
        $capIcon = $iconBox
        $capName = $nameLabel
        $capSub  = $subLabel
        $hoverIn  = {
            $capCard.BackColor = $hoverBg
            $capIcon.BackColor = $hoverBg
            $capName.BackColor = $hoverBg
            $capSub.BackColor  = $hoverBg
        }.GetNewClosure()
        $hoverOut = {
            $capCard.BackColor = $normalBg
            $capIcon.BackColor = $normalBg
            $capName.BackColor = $normalBg
            $capSub.BackColor  = $normalBg
        }.GetNewClosure()
        $card.Add_MouseEnter($hoverIn)
        $card.Add_MouseLeave($hoverOut)
        $nameLabel.Add_MouseEnter($hoverIn); $nameLabel.Add_MouseLeave($hoverOut)
        $subLabel.Add_MouseEnter($hoverIn);  $subLabel.Add_MouseLeave($hoverOut)
        $iconBox.Add_MouseEnter($hoverIn);   $iconBox.Add_MouseLeave($hoverOut)

        # Click handlers (apply profile)
        $capId = $entry.Id
        $click = { if ($OnApply) { & $OnApply $capId } }.GetNewClosure()
        $card.Add_Click($click)
        $nameLabel.Add_Click($click)
        $subLabel.Add_Click($click)
        $iconBox.Add_Click($click)

        $form.Controls.Add($card)
        $y += $cardHeight + $cardGap
    }

    $script:QuickPanelForm    = $form
    $script:QuickPanelVisible = $true
    $form.Show()

    # DWM rounded corners + dark mode + phosphor-cyan border
    try {
        if ("DwmHelper" -as [type]) {
            Apply-DwmWindowEffects -Form $form -CornerStyle 3 -BorderColorRGB @(
                $script:QPPalette.Lagoon.R, $script:QPPalette.Lagoon.G, $script:QPPalette.Lagoon.B
            )
        }
    } catch {}

    # Fade-in (cubic-out feels lighter than linear)
    $qpFade = New-Object System.Windows.Forms.Timer
    $qpFade.Interval = 14
    $captured = $form
    $qpFade.Add_Tick({
        try {
            if ($captured -and -not $captured.IsDisposed) {
                $op = $captured.Opacity + 0.12
                if ($op -ge 0.97) {
                    $captured.Opacity = 0.97
                    $qpFade.Stop(); $qpFade.Dispose()
                } else {
                    $captured.Opacity = $op
                }
            } else { $qpFade.Stop(); $qpFade.Dispose() }
        } catch { try { $qpFade.Stop(); $qpFade.Dispose() } catch {} }
    })
    $qpFade.Start()
}

function Close-QuickPanel {
    <#
    .SYNOPSIS
    Closes the quick panel if it's open.
    #>
    if ($script:QuickPanelForm -and -not $script:QuickPanelForm.IsDisposed) {
        try {
            Clear-QuickPanelGeneratedImages -Root $script:QuickPanelForm
            $script:QuickPanelForm.Hide()
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
