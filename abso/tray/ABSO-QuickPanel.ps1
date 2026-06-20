# ABSO-QuickPanel.ps1 - v3.0 "Phosphor" retro-gaming HUD quick-launch panel
#
# Tron / retro-arcade HUD aesthetic to match ABSO-Notifications.ps1 v5.0.
# Phosphor cyan accent, Bahnschrift Condensed headlines, Cascadia Code body,
# CRT scanlines, L-shaped corner brackets, solid Ink-100 label backgrounds
# (no transparency races).

$script:QuickPanelForm    = $null
$script:QuickPanelVisible = $false
$script:QuickPanelPulseTimer = $null
$script:QuickPanelPulseFrame = 0
$script:QuickPanelPulseTargets = $null
$script:QuickPanelToolTip = $null

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

function Set-QuickPanelPictureImageSafe {
    param(
        [System.Windows.Forms.PictureBox]$PictureBox,
        [AllowNull()][System.Drawing.Image]$Image
    )

    if (-not $PictureBox) {
        if ($Image) {
            try { $Image.Dispose() } catch {}
        }
        return
    }

    $oldImage = $PictureBox.Image
    $PictureBox.Image = $Image
    if ($oldImage -and -not [object]::ReferenceEquals($oldImage, $Image)) {
        try { $oldImage.Dispose() } catch {}
    }
}

function Format-QuickPanelDisplayCopy {
    param([AllowNull()][string]$Text)

    if ([string]::IsNullOrWhiteSpace($Text)) { return "" }
    if (Get-Command Format-TrayDisplayCopy -ErrorAction SilentlyContinue) {
        return (Format-TrayDisplayCopy -Text $Text)
    }
    return "$Text"
}

function Format-QuickPanelUserFacingText {
    param([AllowNull()][string]$Text)

    if ([string]::IsNullOrWhiteSpace($Text)) { return "" }
    if (Get-Command Format-TrayUserFacingText -ErrorAction SilentlyContinue) {
        return (Format-TrayUserFacingText -Text $Text)
    }
    return "$Text"
}

function Stop-QuickPanelPulseTimer {
    if ($script:QuickPanelPulseTimer) {
        try { $script:QuickPanelPulseTimer.Stop() } catch {}
        try { $script:QuickPanelPulseTimer.Dispose() } catch {}
        $script:QuickPanelPulseTimer = $null
    }
    $script:QuickPanelPulseFrame = 0
    $script:QuickPanelPulseTargets = $null
}

function Get-QuickPanelGameGroup {
    param(
        [string]$ProfileId,
        [object]$Profile
    )

    if ($Profile -and -not [string]::IsNullOrWhiteSpace("$($Profile.GameGroup)")) {
        return "$($Profile.GameGroup)"
    }

    $variantSuffixes = @(
        "-online-gsync-hdr", "-gsync-hdr-capture", "-gsync-capture",
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

function Get-QuickPanelCardChipText {
    param(
        [object]$Profile,
        [string]$Kind,
        [bool]$PendingApply = $false,
        [bool]$WindowsRestart = $false,
        [bool]$VerificationInProgress = $false
    )

    if ("$Kind" -eq "active") {
        if ($WindowsRestart) {
            return "RESTART"
        }
        if ($PendingApply) {
            return "FIX"
        }
        if ($VerificationInProgress) {
            return "CHECK"
        }
        return "ACTIVE"
    }
    if ("$Kind" -eq "empty") {
        return "EMPTY"
    }
    if ($Profile -and -not [string]::IsNullOrWhiteSpace("$($Profile.Variant)")) {
        return (Get-QuickPanelCompactChipText -Text "$($Profile.Variant)")
    }
    if ($Profile -and -not [string]::IsNullOrWhiteSpace("$($Profile.SyncMode)")) {
        return (Get-QuickPanelCompactChipText -Text "$($Profile.SyncMode)")
    }
    if ("$Kind" -eq "favorite") {
        return "FAV"
    }
    return ""
}

function Get-QuickPanelCompactChipText {
    param([AllowNull()][string]$Text)

    if ([string]::IsNullOrWhiteSpace($Text)) { return "" }

    $value = (Format-QuickPanelDisplayCopy -Text $Text).Trim()
    if ([string]::IsNullOrWhiteSpace($value)) { return "" }

    switch -Regex ($value) {
        '(?i)capture' { return "CAPTURE" }
        '(?i)console[-\s]?parity' { return "CONSOLE" }
        '(?i)tournament|144\s*hz' { return "144HZ" }
        '(?i)g[-\s]?sync' { return "G-SYNC" }
        '(?i)no\s*sync' { return "NO SYNC" }
        '(?i)low[-\s]?latency' { return "LOW LAT" }
        '(?i)webgl' { return "WEBGL" }
        '(?i)tauri|webview|native' { return "NATIVE" }
        '(?i)universal' { return "UNIV" }
        '(?i)offline' { return "OFFLINE" }
        '(?i)online' { return "ONLINE" }
        '(?i)\bHDR\b' { return "HDR" }
        '(?i)\bSDR\b' { return "SDR" }
        '(?i)agnostic' { return "ANY" }
    }

    $upper = $value.ToUpperInvariant()
    if ($upper.Length -gt 8) { return $upper.Substring(0, 8) }
    return $upper
}

function Get-QuickPanelCardTooltipText {
    param(
        [object]$Profile,
        [string]$Kind,
        [string]$ProfileId,
        [bool]$Disabled = $false,
        [string]$ActivePendingApplyText = "",
        [string]$ActiveWindowsRestartText = "",
        [string]$ActiveVerificationText = ""
    )

    $name = if ($Profile -and -not [string]::IsNullOrWhiteSpace("$($Profile.Name)")) {
        Format-QuickPanelDisplayCopy -Text "$($Profile.Name)"
    }
    elseif (-not [string]::IsNullOrWhiteSpace($ProfileId)) {
        Format-QuickPanelUserFacingText -Text $ProfileId
    }
    else {
        "Quick profile"
    }

    $descriptor = if ($Profile -and -not [string]::IsNullOrWhiteSpace("$($Profile.Sub)")) {
        Format-QuickPanelDisplayCopy -Text "$($Profile.Sub)"
    }
    elseif ($Profile -and -not [string]::IsNullOrWhiteSpace("$($Profile.Cat)")) {
        Format-QuickPanelDisplayCopy -Text "$($Profile.Cat)"
    }
    else {
        ""
    }

    $parts = New-Object System.Collections.Generic.List[string]
    [void]$parts.Add($name)
    if (-not [string]::IsNullOrWhiteSpace($descriptor) -and $descriptor -ne $name) {
        [void]$parts.Add($descriptor)
    }

    if ("$Kind" -eq "empty") {
        if ("$ProfileId" -eq "__quick_panel_empty__") {
            [void]$parts.Add("Status: no quick profiles")
            [void]$parts.Add("No active profile or favorite shortcuts are available.")
        }
        else {
            if (-not [string]::IsNullOrWhiteSpace($ActiveWindowsRestartText)) {
                [void]$parts.Add("Status: Windows restart required")
                [void]$parts.Add("$($ActiveWindowsRestartText.Trim()) needs a Windows restart to finish.")
            }
            elseif (-not [string]::IsNullOrWhiteSpace($ActivePendingApplyText)) {
                [void]$parts.Add("Status: pending profile fixes available")
                [void]$parts.Add("Click applies pending profile fixes for $($ActivePendingApplyText.Trim()).")
            }
            elseif (-not [string]::IsNullOrWhiteSpace($ActiveVerificationText)) {
                [void]$parts.Add("Status: checking profile state")
                [void]$parts.Add("Verifier is reading current settings before showing fixes or reapply.")
            }
            else {
                [void]$parts.Add("Status: profile reference missing")
            }
            [void]$parts.Add("This saved profile id is not in the current profile list.")
        }
    }
    elseif ($Disabled) {
        [void]$parts.Add("Status: disabled shortcut")
        [void]$parts.Add("This card will not apply a profile.")
    }
    elseif ("$Kind" -eq "active") {
        if (-not [string]::IsNullOrWhiteSpace($ActiveWindowsRestartText)) {
            [void]$parts.Add("Status: Windows restart required")
            [void]$parts.Add("$($ActiveWindowsRestartText.Trim()) needs a Windows restart to finish.")
        }
        elseif (-not [string]::IsNullOrWhiteSpace($ActivePendingApplyText)) {
            [void]$parts.Add("Status: pending profile fixes available")
            [void]$parts.Add("Click applies pending profile fixes for $($ActivePendingApplyText.Trim()).")
        }
        elseif (-not [string]::IsNullOrWhiteSpace($ActiveVerificationText)) {
            [void]$parts.Add("Status: checking profile state")
            [void]$parts.Add("Verifier is reading current settings before showing fixes or reapply.")
        }
        else {
            [void]$parts.Add("Status: active profile")
            [void]$parts.Add("Click checks current state first; fixes or reapplies only if needed.")
        }
    }
    elseif ("$Kind" -eq "favorite") {
        [void]$parts.Add("Status: favorite shortcut")
        [void]$parts.Add("Click to apply this profile.")
    }
    else {
        [void]$parts.Add("Status: profile shortcut")
        [void]$parts.Add("Click to apply this profile.")
    }

    return ($parts -join "`n")
}

function Get-QuickPanelHeaderChipText {
    param(
        [object[]]$PanelProfiles = @(),
        [bool]$EmptyPanel = $false,
        [bool]$HasPinnedActiveProfile = $false
    )

    $visibleCount = @($PanelProfiles).Count
    if ($EmptyPanel) {
        $firstEntry = if ($visibleCount -gt 0) { $PanelProfiles[0] } else { $null }
        $firstId = ""
        if ($firstEntry) {
            if ($firstEntry -is [System.Collections.IDictionary] -and $firstEntry.Contains("Id")) {
                $firstId = "$($firstEntry["Id"])"
            }
            elseif ($firstEntry.PSObject.Properties["Id"]) {
                $firstId = "$($firstEntry.Id)"
            }
        }
        if (-not [string]::IsNullOrWhiteSpace($firstId) -and $firstId -ne "__quick_panel_empty__") {
            return "MISSING"
        }
        return "EMPTY"
    }

    if ($HasPinnedActiveProfile) {
        $extraCount = [Math]::Max(0, ($visibleCount - 1))
        if ($extraCount -gt 0) { return "ACTIVE +$extraCount" }
        return "ACTIVE"
    }

    if ($visibleCount -eq 1) { return "1 FAVORITE" }
    return "$visibleCount FAVORITES"
}

function New-QuickPanelGameMedallionBitmap {
    <#
    .SYNOPSIS
    Builds a compact game-mark medallion for quick-panel cards. The raw game
    silhouette stays visible, but the surrounding ring/glow makes the quick
    launcher feel like the tray hero and toast surfaces.
    #>
    param(
        [string]$GameGroup,
        [string]$Category = "Other",
        [System.Drawing.Color]$Color = [System.Drawing.Color]::White,
        [switch]$ActiveBadge,
        [string]$ModeBadge = "",
        [switch]$FavoriteBadge,
        [switch]$PendingApplyBadge,
        [switch]$WindowsRestartBadge,
        [switch]$VerificationBadge,
        [switch]$EmptyBadge
    )

    $mark = $null
    if ($EmptyBadge -and (Get-Command New-ActionBitmap -ErrorAction SilentlyContinue)) {
        # True empty quick-panel state is not a game/profile shortcut; keep it
        # visually distinct from the productivity profile while stale profile
        # empty states still use the profile-id game mark below.
        $mark = New-ActionBitmap -Action "QuickPanel" -Color $Color
    }
    elseif ($ActiveBadge -and (Get-Command New-ActiveGameBitmap -ErrorAction SilentlyContinue)) {
        $mark = New-ActiveGameBitmap `
            -GameGroup $GameGroup `
            -Color $Color `
            -Category $Category `
            -ModeBadge $ModeBadge `
            -FavoriteBadge ([bool]$FavoriteBadge) `
            -PendingApplyBadge ([bool]$PendingApplyBadge) `
            -WindowsRestartBadge ([bool]$WindowsRestartBadge) `
            -VerificationBadge ([bool]$VerificationBadge)
    }
    elseif ($FavoriteBadge -and (Get-Command New-FavoriteGameBitmap -ErrorAction SilentlyContinue)) {
        $mark = New-FavoriteGameBitmap `
            -GameGroup $GameGroup `
            -Color $Color `
            -Category $Category `
            -ModeBadge $ModeBadge
    }
    elseif (-not [string]::IsNullOrWhiteSpace($ModeBadge) -and (Get-Command New-GameSyncBadgeBitmap -ErrorAction SilentlyContinue)) {
        $mark = New-GameSyncBadgeBitmap `
            -GameGroup $GameGroup `
            -Color $Color `
            -Category $Category `
            -SyncMode "agnostic" `
            -ModeBadge $ModeBadge
    }
    elseif (Get-Command New-GameBitmap -ErrorAction SilentlyContinue) {
        $mark = New-GameBitmap -GameGroup $GameGroup -Color $Color -Category $Category
    }
    elseif (Get-Command New-CategoryBitmap -ErrorAction SilentlyContinue) {
        $mark = New-CategoryBitmap -Category $Category -Color $Color
    }
    if (-not $mark) { return $null }

    $bmp = New-Object System.Drawing.Bitmap(30, 30)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $g.Clear([System.Drawing.Color]::Transparent)

    $glowBrush = New-Object System.Drawing.SolidBrush -ArgumentList (
        [System.Drawing.Color]::FromArgb(50, $Color.R, $Color.G, $Color.B)
    )
    $backBrush = New-Object System.Drawing.SolidBrush -ArgumentList $script:QPPalette.Ink100
    $ringPen = New-Object System.Drawing.Pen -ArgumentList (
        [System.Drawing.Color]::FromArgb(170, $Color.R, $Color.G, $Color.B), 1.25
    )
    $arcPen = New-Object System.Drawing.Pen -ArgumentList (
        [System.Drawing.Color]::FromArgb(120, $Color.R, $Color.G, $Color.B), 1.1
    )
    $arcPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
    $arcPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
    $shineBrush = New-Object System.Drawing.SolidBrush -ArgumentList (
        [System.Drawing.Color]::FromArgb(70, 255, 255, 255)
    )

    try {
        $g.FillEllipse($glowBrush, 1, 1, 28, 28)
        $g.FillEllipse($backBrush, 4, 4, 22, 22)
        $g.DrawEllipse($ringPen, 4, 4, 22, 22)
        if ($ActiveBadge) {
            $g.DrawArc($arcPen, 2, 2, 26, 26, 210, 56)
            $g.DrawArc($arcPen, 2, 2, 26, 26, 330, 42)
        }
        $g.DrawImage($mark, (New-Object System.Drawing.Rectangle(7, 7, 16, 16)))
        if ($EmptyBadge) {
            $emptyBadgeBrush = New-Object System.Drawing.SolidBrush -ArgumentList (
                [System.Drawing.Color]::FromArgb(255, 110, 118, 138)
            )
            $emptyBadgePen = New-Object System.Drawing.Pen -ArgumentList (
                [System.Drawing.Color]::FromArgb(235, 232, 234, 240), 1.1
            )
            $emptyBadgePen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
            $emptyBadgePen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
            $g.FillEllipse($emptyBadgeBrush, 21, 21, 7, 7)
            $g.DrawLine($emptyBadgePen, [float]23.0, [float]24.5, [float]26.0, [float]24.5)
            $emptyBadgePen.Dispose()
            $emptyBadgeBrush.Dispose()
        }
        $g.FillEllipse($shineBrush, 8, 6, 7, 3)
    }
    finally {
        $shineBrush.Dispose()
        $arcPen.Dispose()
        $ringPen.Dispose()
        $backBrush.Dispose()
        $glowBrush.Dispose()
        $g.Dispose()
        $mark.Dispose()
    }

    return $bmp
}

function Clear-QuickPanelToolTip {
    if ($script:QuickPanelToolTip) {
        try { $script:QuickPanelToolTip.Dispose() } catch {}
        $script:QuickPanelToolTip = $null
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
        [string]$ActivePendingApplyText = "",
        [string]$ActiveWindowsRestartText = "",
        [string]$ActiveVerificationText = "",
        [string]$EmptyMessage = "No active profile or favorites to show.",
        [string]$EmptyProfileId = "",
        [scriptblock]$OnApply
    )

    _QP-Ensure-Fonts
    Stop-QuickPanelPulseTimer

    if ($script:QuickPanelForm -and -not $script:QuickPanelForm.IsDisposed) {
        try {
            Clear-QuickPanelGeneratedImages -Root $script:QuickPanelForm
            Clear-QuickPanelToolTip
            $script:QuickPanelForm.Hide()
            [System.Windows.Forms.Application]::DoEvents()
            $script:QuickPanelForm.Close()
            $script:QuickPanelForm.Dispose()
        } catch {
            Write-TrayLog "QuickPanel disposal error: $($_.Exception.Message)" -Level "WARN"
        }
        $script:QuickPanelForm = $null
        $script:QuickPanelVisible = $false
        $script:QuickPanelEmptyState = $false
    }

    $maxQuickPanelCards = 3
    $panelProfiles = @()
    $hasPinnedActiveProfile = (
        -not [string]::IsNullOrWhiteSpace($ActiveProfile) -and
        $Profiles -and
        $Profiles.Contains($ActiveProfile)
    )
    if ($hasPinnedActiveProfile) {
        $panelProfiles += @{ Id = $ActiveProfile; Profile = $Profiles[$ActiveProfile]; Kind = "active" }
    }
    foreach ($fav in $Favorites) {
        if ($panelProfiles.Count -ge $maxQuickPanelCards) { break }
        if ($fav -eq $ActiveProfile) { continue }
        if ($Profiles -and $Profiles.Contains($fav)) {
            $panelProfiles += @{ Id = $fav; Profile = $Profiles[$fav]; Kind = "favorite" }
        }
    }
    $emptyPanel = $false
    if ($panelProfiles.Count -eq 0) {
        $emptyPanel = $true
        $emptyText = if ([string]::IsNullOrWhiteSpace($EmptyMessage)) {
            "No active profile or favorites to show."
        }
        else {
            $EmptyMessage.Trim()
        }
        $emptyProfileId = if (-not [string]::IsNullOrWhiteSpace($EmptyProfileId)) {
            $EmptyProfileId.Trim()
        }
        else {
            "__quick_panel_empty__"
        }
        $emptyName = if ($emptyProfileId -ne "__quick_panel_empty__") {
            if (Get-Command Format-TrayUserFacingText -ErrorAction SilentlyContinue) {
                Format-TrayUserFacingText -Text $emptyProfileId
            }
            else {
                $emptyProfileId
            }
        }
        else {
            "No quick profiles"
        }
        $emptyGameGroup = if ($emptyProfileId -ne "__quick_panel_empty__") {
            Get-QuickPanelGameGroup -ProfileId $emptyProfileId -Profile $null
        }
        else {
            "productivity"
        }
        $panelProfiles += @{
            Id = $emptyProfileId
            Profile = [pscustomobject]@{
                Name = $emptyName
                Sub = $emptyText
                Cat = "Other"
                GameGroup = $emptyGameGroup
                Variant = ""
                SyncMode = ""
            }
            Kind = "empty"
            Disabled = $true
        }
    }

    # Phosphor HUD card dimensions
    $panelWidth   = 440
    $cardHeight   = if ($emptyPanel) { 70 } else { 56 }
    $cardGap      = 6
    $padX         = 18
    $padTop       = 14
    $headerHeight = 38
    $padBottom    = 14
    $panelHeight  = $padTop + $headerHeight + ($panelProfiles.Count * ($cardHeight + $cardGap)) - $cardGap + $padBottom

    $form = New-Object System.Windows.Forms.Form
    $form.Text             = ""
    $form.FormBorderStyle  = [System.Windows.Forms.FormBorderStyle]::None
    $form.BackColor        = $script:QPPalette.Ink100
    $form.Size             = New-Object System.Drawing.Size($panelWidth, $panelHeight)
    $form.StartPosition    = [System.Windows.Forms.FormStartPosition]::Manual
    $form.TopMost          = $true
    $form.ShowInTaskbar    = $false
    $form.Opacity          = 0

    Clear-QuickPanelToolTip
    $toolTip = New-Object System.Windows.Forms.ToolTip
    $toolTip.AutoPopDelay = 12000
    $toolTip.InitialDelay = 350
    $toolTip.ReshowDelay = 120
    $toolTip.ShowAlways = $true
    $script:QuickPanelToolTip = $toolTip
    $form.Add_Disposed({ Clear-QuickPanelToolTip })

    $qpInk100 = $script:QPPalette.Ink100
    $qpInk200 = $script:QPPalette.Ink200
    $qpInk300 = $script:QPPalette.Ink300
    $qpPaper = $script:QPPalette.Paper
    $qpMist = $script:QPPalette.Mist
    $qpLagoon = $script:QPPalette.Lagoon

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

    # Panel surface paint: solid Ink-100, L-corner brackets, outline, left
    # phosphor rail, hairline rule under the header. Scanlines were removed
    # because they brightened the form's effective color above pure Ink-100
    # and made the (still-pure-Ink-100) label backgrounds render as darker
    # rectangle cards cut into the lighter surface.
    $capW = $panelWidth
    $capH = $panelHeight
    $form.Add_Paint({
        param($s, $e)
        $g = $e.Graphics
        $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
        $g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::ClearTypeGridFit

        # 1) Solid Ink-100 base (matches Form.BackColor and label backgrounds
        #    so labels composite invisibly into the surface)
        $baseBrush = New-Object System.Drawing.SolidBrush -ArgumentList $qpInk100
        $g.FillRectangle($baseBrush, 0, 0, $capW, $capH)
        $baseBrush.Dispose()

        # 3) Outline (full panel hairline in phosphor cyan at low alpha)
        $outlineColor = [System.Drawing.Color]::FromArgb(80, $qpLagoon.R, $qpLagoon.G, $qpLagoon.B)
        $outlinePen = New-Object System.Drawing.Pen -ArgumentList (
            $outlineColor, 1
        )
        $g.DrawRectangle($outlinePen, 0, 0, ($capW - 1), ($capH - 1))
        $outlinePen.Dispose()

        # 4) Left accent rail - 6px solid phosphor + 1px feather
        $strokeBrush = New-Object System.Drawing.SolidBrush -ArgumentList $qpLagoon
        $g.FillRectangle($strokeBrush, 0, 0, 6, $capH)
        $strokeBrush.Dispose()
        $featherColor = [System.Drawing.Color]::FromArgb(80, $qpLagoon.R, $qpLagoon.G, $qpLagoon.B)
        $featherBrush = New-Object System.Drawing.SolidBrush -ArgumentList (
            $featherColor
        )
        $g.FillRectangle($featherBrush, 6, 0, 1, $capH)
        $featherBrush.Dispose()
        # Tick perforations every 22px - dark notches across the rail
        $tickBrush = New-Object System.Drawing.SolidBrush -ArgumentList $qpInk100
        for ($ty = 14; $ty -lt ($capH - 6); $ty += 22) {
            $g.FillRectangle($tickBrush, 0, $ty, 6, 1)
        }
        $tickBrush.Dispose()

        # 5) L-shaped corner brackets in phosphor cyan (10px arms, 1.6px pen)
        $bracketLen = 10
        $bracketPen = New-Object System.Drawing.Pen -ArgumentList $qpLagoon, 1.6
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
        $rulePen = New-Object System.Drawing.Pen -ArgumentList $qpInk300, 1
        $g.DrawLine($rulePen, $padX, ($padTop + $headerHeight - 4),
            ($capW - $padX), ($padTop + $headerHeight - 4))
        $rulePen.Dispose()

        # 7) Ambient header sweep. This uses the same lightweight timer as the
        # active-card pulse so favorites-only and empty states still feel alive.
        $ambientAlpha = [int](42 + (30 * ([Math]::Sin($script:QuickPanelPulseFrame / 5.0) + 1.0)))
        $ambientX = $padX + (($script:QuickPanelPulseFrame * 6) % [Math]::Max(1, ($capW - ($padX * 2) - 70)))
        $ambientPen = New-Object System.Drawing.Pen -ArgumentList (
            [System.Drawing.Color]::FromArgb($ambientAlpha, $qpLagoon.R, $qpLagoon.G, $qpLagoon.B), 1.0
        )
        $ambientPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
        $ambientPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
        $g.DrawLine($ambientPen, $ambientX, ($padTop + $headerHeight - 8),
            [Math]::Min(($capW - $padX), ($ambientX + 54)), ($padTop + $headerHeight - 8))
        $ambientPen.Dispose()
    }.GetNewClosure())

    # Header eyebrow. Solid Ink-100 BackColor on
    # every label avoids the WinForms transparency race that produced solid
    # rectangles when Discord popped over the toast surface.
    $emptyEyebrowText = if ($emptyPanel) {
        $firstEmptyId = if ($panelProfiles.Count -gt 0) { "$($panelProfiles[0].Id)" } else { "__quick_panel_empty__" }
        if ($firstEmptyId -eq "__quick_panel_empty__") { "QUICK PANEL / EMPTY" } else { "PROFILE LIST / MISSING" }
    }
    else {
        ""
    }
    $eyebrow = New-Object System.Windows.Forms.Label
    $eyebrow.Text      = if ($emptyPanel) { $emptyEyebrowText } elseif ($hasPinnedActiveProfile) { "ACTIVE / QUICK LAUNCH" } else { "FAVORITES / QUICK LAUNCH" }
    $eyebrow.Font      = $script:QPFont_Eyebrow
    $eyebrow.ForeColor = $script:QPPalette.Lagoon
    $eyebrow.BackColor = $script:QPPalette.Ink100
    $eyebrow.Location  = New-Object System.Drawing.Point($padX, $padTop)
    $eyebrow.Size      = New-Object System.Drawing.Size(($panelWidth - $padX * 2 - 124), 14)
    $form.Controls.Add($eyebrow)

    $headerChipText = Get-QuickPanelHeaderChipText `
        -PanelProfiles @($panelProfiles) `
        -EmptyPanel:$emptyPanel `
        -HasPinnedActiveProfile:$hasPinnedActiveProfile
    $headerChip = New-Object System.Windows.Forms.Panel
    $headerChip.Tag       = "__quick_panel_header_chip__"
    $headerChip.Location  = New-Object System.Drawing.Point(($panelWidth - $padX - 108), ($padTop - 1))
    $headerChip.Size      = New-Object System.Drawing.Size(84, 17)
    $headerChip.BackColor = $script:QPPalette.Ink100
    $capHeaderChipText = $headerChipText
    $capHeaderChipFont = $script:QPFont_Eyebrow
    $headerChip.Add_Paint({
        param($s, $e)
        $g = $e.Graphics
        $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
        $g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::ClearTypeGridFit
        $pulse = ([Math]::Sin($script:QuickPanelPulseFrame / 5.0) + 1.0) / 2.0
        $fillAlpha = [int](34 + (18 * $pulse))
        $edgeAlpha = [int](96 + (50 * $pulse))
        $fillBrush = New-Object System.Drawing.SolidBrush -ArgumentList (
            [System.Drawing.Color]::FromArgb($fillAlpha, $qpLagoon.R, $qpLagoon.G, $qpLagoon.B)
        )
        $g.FillRectangle($fillBrush, 0, 1, ($s.Width - 1), ($s.Height - 2))
        $fillBrush.Dispose()

        $edgePen = New-Object System.Drawing.Pen -ArgumentList (
            [System.Drawing.Color]::FromArgb($edgeAlpha, $qpLagoon.R, $qpLagoon.G, $qpLagoon.B), 1
        )
        $g.DrawRectangle($edgePen, 0, 1, ($s.Width - 1), ($s.Height - 3))
        $edgePen.Dispose()

        $sweepPen = New-Object System.Drawing.Pen -ArgumentList (
            [System.Drawing.Color]::FromArgb([int](42 + (32 * $pulse)), $qpPaper.R, $qpPaper.G, $qpPaper.B), 1
        )
        $sweepPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
        $sweepPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
        $sweepX = 4 + (($script:QuickPanelPulseFrame * 3) % [Math]::Max(1, ($s.Width - 26)))
        $g.DrawLine($sweepPen, $sweepX, 3, [Math]::Min(($s.Width - 5), ($sweepX + 18)), 3)
        $sweepPen.Dispose()

        $chipBrush = New-Object System.Drawing.SolidBrush -ArgumentList $qpPaper
        $chipFormat = New-Object System.Drawing.StringFormat
        $chipFormat.Alignment = [System.Drawing.StringAlignment]::Center
        $chipFormat.LineAlignment = [System.Drawing.StringAlignment]::Center
        $chipFormat.Trimming = [System.Drawing.StringTrimming]::EllipsisCharacter
        $chipFormat.FormatFlags = [System.Drawing.StringFormatFlags]::NoWrap
        $g.DrawString($capHeaderChipText, $capHeaderChipFont, $chipBrush, (New-Object System.Drawing.RectangleF(2, 1, ($s.Width - 4), ($s.Height - 2))), $chipFormat)
        $chipFormat.Dispose()
        $chipBrush.Dispose()
    }.GetNewClosure())
    $toolTip.SetToolTip($headerChip, "Quick Panel summary: $headerChipText")
    $form.Controls.Add($headerChip)

    # Close affordance - generated icon button, not a raw text X.
    $closeBox = New-Object System.Windows.Forms.PictureBox
    $closeBox.Location  = New-Object System.Drawing.Point(($panelWidth - $padX - 18), ($padTop - 2))
    $closeBox.Size      = New-Object System.Drawing.Size(18, 18)
    $closeBox.SizeMode  = [System.Windows.Forms.PictureBoxSizeMode]::Zoom
    $closeBox.BackColor = $script:QPPalette.Ink100
    $closeBox.Cursor    = [System.Windows.Forms.Cursors]::Hand
    $closeBox.Image     = New-ActionBitmap -Action "Close" -Color $script:QPPalette.Lagoon
    $toolTip.SetToolTip($closeBox, "Close Quick Panel")
    $closeBox.Add_Click({ Close-QuickPanel })
    $closeBox.Add_MouseEnter({
        Set-QuickPanelPictureImageSafe -PictureBox $this -Image (New-ActionBitmap -Action "Close" -Color $qpPaper)
    }.GetNewClosure())
    $closeBox.Add_MouseLeave({
        Set-QuickPanelPictureImageSafe -PictureBox $this -Image (New-ActionBitmap -Action "Close" -Color $qpLagoon)
    }.GetNewClosure())
    $form.Controls.Add($closeBox)

    # Profile cards
    $y = $padTop + $headerHeight
    $script:QuickPanelPulseTargets = New-Object System.Collections.ArrayList
    [void]$script:QuickPanelPulseTargets.Add($form)
    [void]$script:QuickPanelPulseTargets.Add($headerChip)
    foreach ($entry in $panelProfiles) {
        $catName = $entry.Profile.Cat
        $catColor = if (Get-Command Get-CategoryColor -ErrorAction SilentlyContinue) {
            Get-CategoryColor -Category $catName -Fallback $script:QPPalette.Lagoon
        } else { $script:QPPalette.Lagoon }
        $isActive = ($entry.Id -eq $ActiveProfile)
        $isDisabled = if ($entry.ContainsKey("Disabled")) { [bool]$entry.Disabled } else { $false }
        $gameGroup = Get-QuickPanelGameGroup -ProfileId $entry.Id -Profile $entry.Profile
        $gameColor = if (Get-Command Get-GameAccentColor -ErrorAction SilentlyContinue) {
            Get-GameAccentColor -GameGroup $gameGroup -FallbackColor $catColor
        } else { $catColor }
        $variant = if ($entry.Profile.Variant) { "$($entry.Profile.Variant)" } else { "" }
        $modeBadge = if ("$($entry.Id)" -match '(?i)capture' -or $variant -match '(?i)capture') {
            "capture"
        }
        elseif ($variant -match '(?i)\bHDR\b' -or "$($entry.Id)" -match '(?i)-hdr($|-)' ) {
            "hdr"
        }
        else {
            ""
        }
        $favoriteBadge = (
            "$($entry.Kind)" -eq "favorite" -or
            (@($Favorites) | ForEach-Object { "$_" }) -contains "$($entry.Id)"
        )
        $pendingApplyBadge = ($isActive -and -not [string]::IsNullOrWhiteSpace($ActivePendingApplyText))
        $windowsRestartBadge = ($isActive -and -not [string]::IsNullOrWhiteSpace($ActiveWindowsRestartText))
        $verificationBadge = (
            $isActive -and
            -not $pendingApplyBadge -and
            -not $windowsRestartBadge -and
            -not [string]::IsNullOrWhiteSpace($ActiveVerificationText)
        )
        $emptyBadge = ("$($entry.Kind)" -eq "empty" -and "$($entry.Id)" -eq "__quick_panel_empty__")
        $chipText = Get-QuickPanelCardChipText `
            -Profile $entry.Profile `
            -Kind $entry.Kind `
            -PendingApply $pendingApplyBadge `
            -WindowsRestart $windowsRestartBadge `
            -VerificationInProgress $verificationBadge
        if (
            "$($entry.Kind)" -eq "empty" -and
            -not $emptyBadge -and
            -not $pendingApplyBadge -and
            -not $windowsRestartBadge -and
            -not $verificationBadge
        ) {
            $chipText = "MISSING"
        }
        $tooltipText = Get-QuickPanelCardTooltipText `
            -Profile $entry.Profile `
            -Kind $entry.Kind `
            -ProfileId $entry.Id `
            -Disabled $isDisabled `
            -ActivePendingApplyText $ActivePendingApplyText `
            -ActiveWindowsRestartText $ActiveWindowsRestartText `
            -ActiveVerificationText $ActiveVerificationText

        $card = New-Object System.Windows.Forms.Panel
        $card.Tag      = $entry.Id
        $card.Location = New-Object System.Drawing.Point($padX, $y)
        $card.Size     = New-Object System.Drawing.Size(($panelWidth - $padX * 2), $cardHeight)
        $card.Cursor   = if ($isDisabled) { [System.Windows.Forms.Cursors]::Default } else { [System.Windows.Forms.Cursors]::Hand }
        $card.BackColor = if ($isActive) { $qpInk300 } else { $qpInk200 }

        $capCardColor = $gameColor
        $capCardActive = $isActive
        $capCardLagoon = $qpLagoon
        $capCardChip = $chipText
        $capChipFont = $script:QPFont_Eyebrow
        $stateRailKind = if ($pendingApplyBadge) {
            "fix"
        }
        elseif ($windowsRestartBadge) {
            "restart"
        }
        elseif ($verificationBadge) {
            "check"
        }
        elseif ($emptyBadge -or $isDisabled) {
            "missing"
        }
        elseif ($isActive) {
            "active"
        }
        elseif ($favoriteBadge) {
            "favorite"
        }
        else {
            "profile"
        }
        $stateRailColor = switch ($stateRailKind) {
            "fix" { [System.Drawing.Color]::FromArgb(255, 255, 187, 80) }
            "restart" { [System.Drawing.Color]::FromArgb(255, 255, 126, 54) }
            "check" { [System.Drawing.Color]::FromArgb(255, 96, 180, 255) }
            "missing" { $script:QPPalette.Fog }
            "favorite" { [System.Drawing.Color]::FromArgb(255, 229, 165, 71) }
            default { $gameColor }
        }
        $capStateRailKind = $stateRailKind
        $capStateRailColor = $stateRailColor
        $card.Add_Paint({
            param($s, $e)
            $g = $e.Graphics
            $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias

            # 3px left accent stroke - active = full saturation, inactive = subtle
            $barAlpha = if ($capCardActive) { 220 } else { 80 }
            $bar = New-Object System.Drawing.SolidBrush -ArgumentList (
                [System.Drawing.Color]::FromArgb($barAlpha, $capCardColor.R, $capCardColor.G, $capCardColor.B)
            )
            $g.FillRectangle($bar, 0, 0, 3, $s.Height)
            $bar.Dispose()

            # Top-right indicator pip - 2x2 phosphor-cyan dot
            $pipBrush = New-Object System.Drawing.SolidBrush -ArgumentList $capCardLagoon
            $g.FillRectangle($pipBrush, ($s.Width - 5), 3, 2, 2)
            $pipBrush.Dispose()

            # Bottom hairline rule
            $rulePen = New-Object System.Drawing.Pen -ArgumentList (
                [System.Drawing.Color]::FromArgb(50, 255, 255, 255), 1
            )
            $g.DrawLine($rulePen, 12, ($s.Height - 1), ($s.Width - 8), ($s.Height - 1))
            $rulePen.Dispose()

            # Right state rail: non-layout visual state channel for active/fix/restart/check cards.
            $railX = $s.Width - 11
            $railTop = 26
            $railHeight = [Math]::Max(18, ($s.Height - 34))
            $railBack = New-Object System.Drawing.SolidBrush -ArgumentList (
                [System.Drawing.Color]::FromArgb(35, $capStateRailColor.R, $capStateRailColor.G, $capStateRailColor.B)
            )
            $g.FillRectangle($railBack, $railX, $railTop, 3, $railHeight)
            $railBack.Dispose()

            $railAlpha = if ($capStateRailKind -in @("fix", "restart", "check", "active")) {
                [int](115 + (55 * ([Math]::Sin($script:QuickPanelPulseFrame / 4.0) + 1.0)))
            }
            else {
                82
            }
            $railBrush = New-Object System.Drawing.SolidBrush -ArgumentList (
                [System.Drawing.Color]::FromArgb($railAlpha, $capStateRailColor.R, $capStateRailColor.G, $capStateRailColor.B)
            )
            $g.FillRectangle($railBrush, $railX, $railTop, 3, $railHeight)
            $railBrush.Dispose()

            $tickPen = New-Object System.Drawing.Pen -ArgumentList (
                [System.Drawing.Color]::FromArgb(95, $capStateRailColor.R, $capStateRailColor.G, $capStateRailColor.B), 1
            )
            for ($tickY = $railTop; $tickY -lt ($railTop + $railHeight); $tickY += 7) {
                $g.DrawLine($tickPen, ($railX - 3), $tickY, ($railX - 1), $tickY)
            }
            $tickPen.Dispose()

            if ($capStateRailKind -in @("fix", "restart", "check")) {
                $scanY = $railTop + (($script:QuickPanelPulseFrame * 3) % [Math]::Max(1, $railHeight))
                $scanPen = New-Object System.Drawing.Pen -ArgumentList (
                    [System.Drawing.Color]::FromArgb(220, $capCardLagoon.R, $capCardLagoon.G, $capCardLagoon.B), 1.2
                )
                $scanPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
                $scanPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
                $g.DrawLine($scanPen, ($railX - 4), $scanY, ($railX + 6), $scanY)
                $scanPen.Dispose()
            }

            # Active indicator dot, right side
            if ($capCardActive) {
                $sweepAlpha = [int](55 + (30 * ([Math]::Sin($script:QuickPanelPulseFrame / 4.0) + 1.0)))
                $sweepPen = New-Object System.Drawing.Pen -ArgumentList (
                    [System.Drawing.Color]::FromArgb($sweepAlpha, $capCardColor.R, $capCardColor.G, $capCardColor.B), 1
                )
                $g.DrawLine($sweepPen, 6, 1, ($s.Width - 10), 1)
                $sweepPen.Dispose()

                $pulseAlpha = [int](70 + (45 * ([Math]::Sin($script:QuickPanelPulseFrame / 3.0) + 1.0)))
                $dotGlow = New-Object System.Drawing.SolidBrush -ArgumentList (
                    [System.Drawing.Color]::FromArgb($pulseAlpha, $capCardColor.R, $capCardColor.G, $capCardColor.B)
                )
                $g.FillEllipse($dotGlow, ($s.Width - 24), (($s.Height / 2) - 8), 16, 16)
                $dotGlow.Dispose()
                $dotBrush = New-Object System.Drawing.SolidBrush -ArgumentList $capCardColor
                $g.FillEllipse($dotBrush, ($s.Width - 19), (($s.Height / 2) - 3), 6, 6)
                $dotBrush.Dispose()
            }

            # Compact chip: active status, variant, sync mode, or favorite marker.
            if (-not [string]::IsNullOrWhiteSpace($capCardChip)) {
                $chipRect = New-Object System.Drawing.Rectangle(($s.Width - 96), 8, 72, 15)
                $chipAlpha = if ($capCardActive) {
                    [int](75 + (25 * ([Math]::Sin($script:QuickPanelPulseFrame / 4.0) + 1.0)))
                }
                else { 42 }
                $chipBack = New-Object System.Drawing.SolidBrush -ArgumentList (
                    [System.Drawing.Color]::FromArgb($chipAlpha, $capCardColor.R, $capCardColor.G, $capCardColor.B)
                )
                $g.FillRectangle($chipBack, $chipRect)
                $chipBack.Dispose()

                $chipPenAlpha = if ($capCardActive) { 190 } else { 85 }
                $chipPen = New-Object System.Drawing.Pen -ArgumentList (
                    [System.Drawing.Color]::FromArgb($chipPenAlpha, $capCardColor.R, $capCardColor.G, $capCardColor.B), 1
                )
                $g.DrawRectangle($chipPen, $chipRect)
                $chipPen.Dispose()

                $chipBrush = New-Object System.Drawing.SolidBrush -ArgumentList $capCardLagoon
                $chipFormat = New-Object System.Drawing.StringFormat
                $chipFormat.Alignment = [System.Drawing.StringAlignment]::Center
                $chipFormat.LineAlignment = [System.Drawing.StringAlignment]::Center
                $chipFormat.Trimming = [System.Drawing.StringTrimming]::EllipsisCharacter
                $chipFormat.FormatFlags = [System.Drawing.StringFormatFlags]::NoWrap
                $chipTextRect = New-Object System.Drawing.RectangleF(
                    [float]$chipRect.X,
                    [float]$chipRect.Y,
                    [float]$chipRect.Width,
                    [float]$chipRect.Height
                )
                $g.DrawString($capCardChip, $capChipFont, $chipBrush, $chipTextRect, $chipFormat)
                $chipFormat.Dispose()
                $chipBrush.Dispose()
            }
        }.GetNewClosure())

        # Icon medallion (game-specific title mark, 30x30 centered vertically).
        # Card background colors (Ink-200/Ink-300) are used for the picture
        # box BackColor so the icon composites cleanly onto the card surface.
        $cardBg = $card.BackColor
        $iconBox = New-Object System.Windows.Forms.PictureBox
        $iconBox.Location = New-Object System.Drawing.Point(9, (($cardHeight / 2) - 15))
        $iconBox.Size = New-Object System.Drawing.Size(30, 30)
        $iconBox.SizeMode = [System.Windows.Forms.PictureBoxSizeMode]::Zoom
        $iconBox.BackColor = $cardBg
        $iconBox.Cursor = if ($isDisabled) { [System.Windows.Forms.Cursors]::Default } else { [System.Windows.Forms.Cursors]::Hand }
        $iconBox.Image = New-QuickPanelGameMedallionBitmap `
            -GameGroup $gameGroup `
            -Color $gameColor `
            -Category $catName `
            -ActiveBadge:$isActive `
            -ModeBadge $modeBadge `
            -FavoriteBadge:$favoriteBadge `
            -PendingApplyBadge:$pendingApplyBadge `
            -WindowsRestartBadge:$windowsRestartBadge `
            -VerificationBadge:$verificationBadge `
            -EmptyBadge:$emptyBadge
        $card.Controls.Add($iconBox)

        # Profile name (Bahnschrift SemiBold Condensed HUD headline, paper)
        $nameLabel = New-Object System.Windows.Forms.Label
        $nameLabel.Text      = if ($entry.Profile -and -not [string]::IsNullOrWhiteSpace("$($entry.Profile.Name)")) {
            Format-QuickPanelDisplayCopy -Text "$($entry.Profile.Name)"
        }
        elseif ($entry.Id) {
            Format-QuickPanelUserFacingText -Text "$($entry.Id)"
        }
        else {
            "Quick profile"
        }
        $nameLabel.Location  = New-Object System.Drawing.Point(48, 8)
        $nameLabel.Size      = New-Object System.Drawing.Size(($panelWidth - $padX * 2 - 152), 20)
        $nameLabel.ForeColor = $script:QPPalette.Paper
        $nameLabel.Font      = $script:QPFont_Title
        $nameLabel.BackColor = $cardBg
        $nameLabel.Cursor    = if ($isDisabled) { [System.Windows.Forms.Cursors]::Default } else { [System.Windows.Forms.Cursors]::Hand }
        $nameLabel.AutoEllipsis = $true
        $card.Controls.Add($nameLabel)

        # Sub-text (Cascadia Code mist) - profile descriptor
        $subText = if ($entry.Profile -and -not [string]::IsNullOrWhiteSpace("$($entry.Profile.Sub)")) {
            Format-QuickPanelDisplayCopy -Text "$($entry.Profile.Sub)"
        }
        elseif ($entry.Profile -and -not [string]::IsNullOrWhiteSpace("$($entry.Profile.Cat)")) {
            Format-QuickPanelDisplayCopy -Text "$($entry.Profile.Cat)"
        }
        else {
            ""
        }
        $subLabel = New-Object System.Windows.Forms.Label
        $subLabel.Text      = $subText
        $subLabel.Location  = New-Object System.Drawing.Point(48, 30)
        $subLabel.Size      = if ($isDisabled) {
            New-Object System.Drawing.Size(($panelWidth - $padX * 2 - 76), 32)
        }
        else {
            # The subtitle sits on its own row below the chip (y=30), so it only
            # needs to clear the ~11px right state rail - give it near-full card
            # width instead of reserving the title-row chip's 152px gutter.
            New-Object System.Drawing.Size(($panelWidth - $padX * 2 - 72), 16)
        }
        $subLabel.ForeColor = $script:QPPalette.Mist
        $subLabel.Font      = $script:QPFont_Sub
        $subLabel.BackColor = $cardBg
        $subLabel.Cursor    = if ($isDisabled) { [System.Windows.Forms.Cursors]::Default } else { [System.Windows.Forms.Cursors]::Hand }
        $subLabel.AutoEllipsis = $true
        $card.Controls.Add($subLabel)

        $toolTip.SetToolTip($card, $tooltipText)
        $toolTip.SetToolTip($iconBox, $tooltipText)
        $toolTip.SetToolTip($nameLabel, $tooltipText)
        $toolTip.SetToolTip($subLabel, $tooltipText)

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
        if (-not $isDisabled) {
            $capId = $entry.Id
            $click = { if ($OnApply) { & $OnApply $capId } }.GetNewClosure()
            $card.Add_Click($click)
            $nameLabel.Add_Click($click)
            $subLabel.Add_Click($click)
            $iconBox.Add_Click($click)
        }

        $form.Controls.Add($card)
        if ($isActive) {
            [void]$script:QuickPanelPulseTargets.Add($card)
        }
        $y += $cardHeight + $cardGap
    }

    $script:QuickPanelForm    = $form
    $script:QuickPanelVisible = $true
    $script:QuickPanelEmptyState = $emptyPanel
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

    if ($script:QuickPanelPulseTargets -and $script:QuickPanelPulseTargets.Count -gt 0) {
        $pulseTimer = New-Object System.Windows.Forms.Timer
        $pulseTimer.Interval = 80
        $pulseTimer.Add_Tick({
            try {
                $script:QuickPanelPulseFrame = ($script:QuickPanelPulseFrame + 1) % 60
                foreach ($target in @($script:QuickPanelPulseTargets)) {
                    if ($target -and -not $target.IsDisposed) {
                        $target.Invalidate()
                    }
                }
            }
            catch {
                Stop-QuickPanelPulseTimer
            }
        })
        $script:QuickPanelPulseTimer = $pulseTimer
        $pulseTimer.Start()
    }
}

function Close-QuickPanel {
    <#
    .SYNOPSIS
    Closes the quick panel if it's open.
    #>
    Stop-QuickPanelPulseTimer
    if ($script:QuickPanelForm -and -not $script:QuickPanelForm.IsDisposed) {
        try {
            Clear-QuickPanelGeneratedImages -Root $script:QuickPanelForm
            Clear-QuickPanelToolTip
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
    $script:QuickPanelEmptyState = $false
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
        [string]$ActivePendingApplyText = "",
        [string]$ActiveWindowsRestartText = "",
        [string]$ActiveVerificationText = "",
        [string]$EmptyMessage = "No active profile or favorites to show.",
        [string]$EmptyProfileId = "",
        [scriptblock]$OnApply
    )
    if ($script:QuickPanelVisible) {
        Show-QuickPanel -Favorites $Favorites -Profiles $Profiles -ActiveProfile $ActiveProfile -ActivePendingApplyText $ActivePendingApplyText -ActiveWindowsRestartText $ActiveWindowsRestartText -ActiveVerificationText $ActiveVerificationText -EmptyMessage $EmptyMessage -EmptyProfileId $EmptyProfileId -OnApply $OnApply
    }
}
