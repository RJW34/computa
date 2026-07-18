# ABSO-Settings.ps1 - Settings panel and config persistence for computa tray

$script:ConfigDir = Join-Path $env:APPDATA "ABSO"
$script:ConfigFile = Join-Path $script:ConfigDir "tray-config.json"
$script:SettingsForm = $null

# ============================================================================
# CONFIG MANAGEMENT
# ============================================================================

function Get-DefaultConfig {
    <#
    .SYNOPSIS
    Returns the default configuration hashtable.
    #>
    return @{
        favorites       = @()
        defaultProfile  = $null
        soundVolume     = 0.2
        soundEnabled    = $true
        notificationsEnabled = $true
        hotkeys         = @{
            openMenu = "Ctrl+Shift+A"
            restore  = "Ctrl+Shift+R"
        }
        showQuickPanel  = $false
        animationSpeed  = "normal"
        # Icon/sound theme pack: a folder name under abso/tray/themes/.
        # Takes effect on tray restart. See themes/README.md.
        theme           = "default"
        # Per-machine tray curation: profile ids listed here stay applyable
        # from the CLI but are hidden from the tray menu/quick panel (e.g.
        # hide the SDR lanes on a machine that runs HDR exclusively).
        hiddenProfiles  = @()
        recentProfiles  = @()
        profileHistory  = @()
        lastProfileState = $null
        lastStartupResolution = $null
        # When true, the launch sanitizer also stops the opt-in tier:
        # cloud sync daemons (OneDrive, Dropbox) and OEM RGB daemons
        # (Razer Synapse, Logitech G HUB, iCUE, Armoury Crate). Default
        # OFF so the user does not lose mid-session cloud uploads or RGB
        # hotkey control without explicitly opting in.
        aggressiveProcessJanitor = $false
        # ProBalance governor: spawn the cpu-balance daemon for a game session
        # to demote background CPU spikers (never the game/anti-cheat/protected
        # images) and auto-restore them. Default OFF — spawning a background
        # daemon is an explicit per-machine opt-in.
        cpuBalancer = $false
        # Tier B (require cpuBalancer ON; the daemon hosts them). Default OFF.
        #   cpuSets:  soft-steer the game toward P-cores (CPU Sets, anti-cheat-safe).
        #   ecoMode:  herd busy background images onto E-cores (EcoQoS); populate
        #             efficiency_mode.background_images in abso.yaml to pick targets.
        #   watchdog: evaluate declarative watchdog.rules (abso.yaml) with
        #             reversible demote/throttle/trim actions; online profiles are
        #             auto-restricted to demote-only.
        cpuSets = $false
        ecoMode = $false
        watchdog = $false
        # Keep-Awake: inhibit system/display sleep while a keep-awake profile's
        # game runs (emulators). Allowed by default; the per-profile catalog flag
        # decides which profiles actually assert it (shooters do not).
        keepAwakeWhileGaming = $true
    }
}

function Read-TrayConfig {
    <#
    .SYNOPSIS
    Reads the tray config from disk, creating defaults if missing or corrupt.
    #>
    $defaults = Get-DefaultConfig

    if (-not (Test-Path $script:ConfigDir)) {
        New-Item -Path $script:ConfigDir -ItemType Directory -Force -ErrorAction SilentlyContinue | Out-Null
    }

    if (Test-Path $script:ConfigFile) {
        try {
            $json = Get-Content $script:ConfigFile -Raw -ErrorAction Stop | ConvertFrom-Json
            $config = @{}

            # Merge with defaults (backward compatibility)
            foreach ($key in $defaults.Keys) {
                if ($null -ne $json.$key) {
                    $val = $json.$key
                    # Convert PSCustomObject arrays to proper arrays
                    if ($val -is [System.Object[]]) {
                        $config[$key] = @($val)
                    }
                    elseif ($val -is [PSCustomObject]) {
                        $ht = @{}
                        $val.PSObject.Properties | ForEach-Object { $ht[$_.Name] = $_.Value }
                        $config[$key] = $ht
                    }
                    else {
                        $config[$key] = $val
                    }
                }
                else {
                    $config[$key] = $defaults[$key]
                }
            }
            return $config
        }
        catch {
            # Corrupt config - back up corrupt file, then reset to defaults
            # Clean old corrupt backups first (keep at most 3)
            try {
                $corruptFiles = Get-ChildItem -Path $script:ConfigDir -Filter "tray-config.json.corrupt.*" -ErrorAction SilentlyContinue |
                    Sort-Object LastWriteTime -Descending |
                    Select-Object -Skip 2
                foreach ($old in $corruptFiles) {
                    Remove-Item $old.FullName -Force -ErrorAction SilentlyContinue
                }
            } catch {}
            $backupPath = "$($script:ConfigFile).corrupt.$(Get-Date -Format 'yyyyMMdd-HHmmss')"
            try {
                Copy-Item $script:ConfigFile $backupPath -Force -ErrorAction SilentlyContinue
            } catch {}
            Write-Warning "ABSO: Corrupt config backed up to $backupPath, resetting to defaults"
        }
    }

    # Write defaults
    Save-TrayConfig $defaults
    return $defaults
}

function Save-TrayConfig {
    <#
    .SYNOPSIS
    Saves the tray config to disk atomically.

    .DESCRIPTION
    Writes the serialized JSON to a temp sibling file, then Move-Item -Force
    swaps it into place. A crash or abrupt kill mid-write leaves either the
    prior config (if the rename never happened) or the new one — never a
    half-written file that the next Read-TrayConfig would flag as corrupt
    and reset to defaults. Fixes the favorites/hotkey-loss class of bug.
    #>
    param([hashtable]$Config)

    if (-not (Test-Path $script:ConfigDir)) {
        New-Item -Path $script:ConfigDir -ItemType Directory -Force -ErrorAction SilentlyContinue | Out-Null
    }

    $tmpFile = "$($script:ConfigFile).tmp-$([Guid]::NewGuid().ToString('N').Substring(0,8))"
    try {
        $jsonText = $Config | ConvertTo-Json -Depth 6
        # Write UTF-8 without BOM — Python consumers read plain UTF-8.
        [System.IO.File]::WriteAllText(
            $tmpFile,
            $jsonText,
            (New-Object System.Text.UTF8Encoding($false))
        )
        Move-Item -LiteralPath $tmpFile -Destination $script:ConfigFile -Force -ErrorAction Stop
    }
    catch {
        $errMsg = "Failed to save config atomically: $($_.Exception.Message)"
        Write-Warning "ABSO: $errMsg"
        if (Get-Command Write-TrayLog -ErrorAction SilentlyContinue) {
            Write-TrayLog $errMsg -Level "ERROR"
        }
        # Clean up stray temp file so we don't accumulate .tmp-* siblings.
        try {
            if (Test-Path -LiteralPath $tmpFile) {
                Remove-Item -LiteralPath $tmpFile -Force -ErrorAction SilentlyContinue
            }
        } catch {}
    }
}

function Get-SettingsProfileGameGroup {
    param(
        [string]$ProfileId,
        [object]$Profile
    )

    if ($Profile -and -not [string]::IsNullOrWhiteSpace("$($Profile.GameGroup)")) {
        return "$($Profile.GameGroup)"
    }

    $variantSuffixes = @(
        "-online-gsync-hdr-capture", "-online-gsync-hdr",
        "-gsync-hdr-capture", "-gsync-capture",
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

function Get-SelectedDefaultProfileId {
    param([System.Windows.Forms.ComboBox]$ComboBox)

    if (-not $ComboBox -or $ComboBox.SelectedIndex -le 0 -or -not $ComboBox.SelectedItem) {
        return $null
    }

    return ($ComboBox.SelectedItem.ToString() -split ' - ', 2)[0]
}

function Get-SettingsProfileDisplayName {
    param(
        [string]$ProfileId,
        [object]$Profile = $null
    )

    if ($Profile -and -not [string]::IsNullOrWhiteSpace("$($Profile.Name)")) {
        if (Get-Command Format-TrayDisplayCopy -ErrorAction SilentlyContinue) {
            return (Format-TrayDisplayCopy -Text "$($Profile.Name)")
        }
        return "$($Profile.Name)"
    }
    if (Get-Command Format-TrayUserFacingText -ErrorAction SilentlyContinue) {
        return (Format-TrayUserFacingText -Text $ProfileId)
    }
    return "$ProfileId"
}

function Get-SettingsProfileModeBadge {
    param(
        [string]$ProfileId,
        [object]$Profile,
        [string]$Variant = ""
    )

    $variantText = if (-not [string]::IsNullOrWhiteSpace($Variant)) {
        $Variant
    }
    elseif ($Profile -and $Profile.Variant) {
        "$($Profile.Variant)"
    }
    elseif ($Profile -and $Profile.Sub) {
        "$($Profile.Sub)"
    }
    else {
        ""
    }

    if ("$ProfileId" -match '(?i)capture' -or $variantText -match '(?i)capture') {
        return "capture"
    }
    if ($variantText -match '(?i)\bHDR\b' -or "$ProfileId" -match '(?i)-hdr($|-)' ) {
        return "hdr"
    }
    return ""
}

function New-SettingsPreviewMedallionBitmap {
    <#
    .SYNOPSIS
    Wraps the reminder-profile mark in a compact settings medallion so the
    settings panel shares the same game identity treatment as the tray menu,
    quick panel, and profile toasts.
    #>
    param(
        [System.Drawing.Image]$Mark,
        [System.Drawing.Color]$Color = [System.Drawing.Color]::FromArgb(255, 245, 184, 64),
        [switch]$WarningBadge
    )

    if (-not $Mark) { return $null }

    $bmp = New-Object System.Drawing.Bitmap(32, 32)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $g.Clear([System.Drawing.Color]::Transparent)

    $backColor = [System.Drawing.Color]::FromArgb(255, 13, 42, 50)
    $glowBrush = New-Object System.Drawing.SolidBrush -ArgumentList (
        [System.Drawing.Color]::FromArgb(48, $Color.R, $Color.G, $Color.B)
    )
    $backBrush = New-Object System.Drawing.SolidBrush -ArgumentList $backColor
    $ringPen = New-Object System.Drawing.Pen -ArgumentList (
        [System.Drawing.Color]::FromArgb(170, $Color.R, $Color.G, $Color.B), 1.25
    )
    $arcPen = New-Object System.Drawing.Pen -ArgumentList (
        [System.Drawing.Color]::FromArgb(115, $Color.R, $Color.G, $Color.B), 1
    )
    $arcPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
    $arcPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
    $shineBrush = New-Object System.Drawing.SolidBrush -ArgumentList (
        [System.Drawing.Color]::FromArgb(64, 255, 255, 255)
    )
    $badgeBrush = New-Object System.Drawing.SolidBrush -ArgumentList (
        [System.Drawing.Color]::FromArgb(255, 245, 120, 92)
    )

    try {
        $g.FillEllipse($glowBrush, 0, 0, 32, 32)
        $g.FillEllipse($backBrush, 4, 4, 24, 24)
        $g.DrawEllipse($ringPen, 4, 4, 24, 24)
        $g.DrawArc($arcPen, 2, 2, 28, 28, 215, 48)
        $g.DrawArc($arcPen, 2, 2, 28, 28, 330, 38)
        $g.DrawImage($Mark, (New-Object System.Drawing.Rectangle(8, 8, 16, 16)))
        $g.FillEllipse($shineBrush, 9, 6, 8, 3)
        if ($WarningBadge) {
            $g.FillEllipse($badgeBrush, 22, 22, 7, 7)
            $badgeMarkPen = New-Object System.Drawing.Pen -ArgumentList ([System.Drawing.Color]::White), 1.0
            $badgeMarkPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
            $badgeMarkPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
            $g.DrawLine($badgeMarkPen, [float]25.5, [float]23.5, [float]25.5, [float]26.0)
            $badgeMarkPen.Dispose()
            $badgeMarkBrush = New-Object System.Drawing.SolidBrush -ArgumentList ([System.Drawing.Color]::White)
            $g.FillEllipse($badgeMarkBrush, [float]24.9, [float]27.0, [float]1.2, [float]1.2)
            $badgeMarkBrush.Dispose()
        }
    }
    finally {
        $badgeBrush.Dispose()
        $shineBrush.Dispose()
        $arcPen.Dispose()
        $ringPen.Dispose()
        $backBrush.Dispose()
        $glowBrush.Dispose()
        $g.Dispose()
        $Mark.Dispose()
    }

    return $bmp
}

function Get-SettingsHeaderChipText {
    param(
        [hashtable]$Config
    )

    if (-not $Config) {
        return "NOT SET"
    }

    $enabledCount = 0
    if ([bool]$Config.notificationsEnabled) { $enabledCount++ }
    if ([bool]$Config.showQuickPanel) { $enabledCount++ }
    if ([bool]$Config.soundEnabled) { $enabledCount++ }

    return "$enabledCount/3 ON"
}

function New-SettingsBrandHeaderPanel {
    <#
    .SYNOPSIS
    Builds the branded settings header used at the top of the tray settings
    dialog. The animated sweep is driven only by a local WinForms timer while
    the settings window is open.
    #>
    param(
        [System.Drawing.Color]$Accent = [System.Drawing.Color]::FromArgb(255, 0, 245, 212),
        [string]$ChipText = "TRAY"
    )

    $panel = New-Object System.Windows.Forms.Panel
    $panel.Size = New-Object System.Drawing.Size(380, 64)
    $panel.BackColor = [System.Drawing.Color]::FromArgb(255, 7, 24, 29)
    $panel.Tag = @{
        Accent = $Accent
        Frame = 0
    }
    $panel.Add_Paint({
        param($s, $e)
        $g = $e.Graphics
        $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
        $state = if ($s.Tag -is [hashtable]) { $s.Tag } else { @{} }
        $accent = if ($state.ContainsKey("Accent") -and $state["Accent"] -is [System.Drawing.Color]) {
            $state["Accent"]
        } else {
            [System.Drawing.Color]::FromArgb(255, 0, 245, 212)
        }
        $frame = if ($state.ContainsKey("Frame")) { [int]$state["Frame"] } else { 0 }

        $rect = New-Object System.Drawing.Rectangle(0, 0, [Math]::Max(1, $s.Width), [Math]::Max(1, $s.Height))
        $bgBrush = New-Object System.Drawing.Drawing2D.LinearGradientBrush(
            $rect,
            [System.Drawing.Color]::FromArgb(255, 7, 24, 29),
            [System.Drawing.Color]::FromArgb(255, 16, 52, 60),
            [System.Drawing.Drawing2D.LinearGradientMode]::ForwardDiagonal
        )
        $g.FillRectangle($bgBrush, $rect)
        $bgBrush.Dispose()

        $railBrush = New-Object System.Drawing.SolidBrush(
            [System.Drawing.Color]::FromArgb(220, $accent.R, $accent.G, $accent.B)
        )
        $g.FillRectangle($railBrush, 0, 0, 4, $s.Height)
        $railBrush.Dispose()

        $orbitStart = ($frame * 9) % 360
        $orbitPen = New-Object System.Drawing.Pen(
            [System.Drawing.Color]::FromArgb(150, $accent.R, $accent.G, $accent.B), 1.3
        )
        $orbitPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
        $orbitPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
        $g.DrawArc($orbitPen, 14, 12, 40, 40, $orbitStart, 86)
        $orbitPen.Dispose()

        $sweepX = 72 + (($frame * 7) % [Math]::Max(1, $s.Width - 150))
        $sweepPen = New-Object System.Drawing.Pen(
            [System.Drawing.Color]::FromArgb(90, $accent.R, $accent.G, $accent.B), 1.0
        )
        $sweepPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
        $sweepPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
        $g.DrawLine($sweepPen, $sweepX, 8, [Math]::Min($s.Width - 12, $sweepX + 58), 8)
        $sweepPen.Dispose()

        $borderPen = New-Object System.Drawing.Pen(
            [System.Drawing.Color]::FromArgb(80, $accent.R, $accent.G, $accent.B), 1
        )
        $g.DrawRectangle($borderPen, 0, 0, ($s.Width - 1), ($s.Height - 1))
        $borderPen.Dispose()
    })

    $brandBox = New-Object System.Windows.Forms.PictureBox
    $brandBox.Location = New-Object System.Drawing.Point(18, 14)
    $brandBox.Size = New-Object System.Drawing.Size(36, 36)
    $brandBox.SizeMode = [System.Windows.Forms.PictureBoxSizeMode]::Zoom
    $brandBox.BackColor = $panel.BackColor
    if (Get-Command New-ActionBitmap -ErrorAction SilentlyContinue) {
        $brandBox.Image = New-ActionBitmap -Action "Brand" -Color $Accent
    }
    $panel.Controls.Add($brandBox)

    $title = New-Object System.Windows.Forms.Label
    $title.Text = "TRAY SETTINGS"
    $title.Location = New-Object System.Drawing.Point(70, 12)
    $title.Size = New-Object System.Drawing.Size(190, 20)
    $title.ForeColor = [System.Drawing.Color]::FromArgb(255, 225, 244, 240)
    $title.BackColor = $panel.BackColor
    $title.Font = New-Object System.Drawing.Font("Segoe UI Semibold", 10, [System.Drawing.FontStyle]::Bold)
    $title.AutoEllipsis = $true
    $panel.Controls.Add($title)

    $subtitle = New-Object System.Windows.Forms.Label
    $subtitle.Text = "Reminder, surfaces, audio, hotkeys"
    $subtitle.Location = New-Object System.Drawing.Point(70, 34)
    $subtitle.Size = New-Object System.Drawing.Size(210, 16)
    $subtitle.ForeColor = [System.Drawing.Color]::FromArgb(255, 148, 183, 182)
    $subtitle.BackColor = $panel.BackColor
    $subtitle.Font = New-Object System.Drawing.Font("Consolas", 7.5)
    $subtitle.AutoEllipsis = $true
    $panel.Controls.Add($subtitle)

    $chip = New-Object System.Windows.Forms.Label
    $chipTextValue = if ([string]::IsNullOrWhiteSpace($ChipText)) { "TRAY" } else { $ChipText.Trim().ToUpperInvariant() }
    $chip.Text = $chipTextValue
    $chip.Location = New-Object System.Drawing.Point(276, 18)
    $chip.Size = New-Object System.Drawing.Size(82, 18)
    $chip.TextAlign = [System.Drawing.ContentAlignment]::MiddleCenter
    $chip.ForeColor = [System.Drawing.Color]::FromArgb(255, 228, 246, 242)
    $chip.BackColor = [System.Drawing.Color]::FromArgb(255, 16, 52, 60)
    $chip.Font = New-Object System.Drawing.Font("Segoe UI Semibold", 7.5, [System.Drawing.FontStyle]::Bold)
    $chip.AutoEllipsis = $true
    $chip.AccessibleName = "Tray settings state"
    $chip.AccessibleDescription = "Enabled tray popups, Quick Panel restore, and audio cues"
    $panel.Controls.Add($chip)

    return $panel
}

function New-SettingsSectionHeaderPanel {
    param(
        [string]$Text,
        [string]$Action,
        [System.Drawing.Color]$Color
    )

    $panel = New-Object System.Windows.Forms.Panel
    $panel.Size = New-Object System.Drawing.Size(350, 24)
    $panel.BackColor = [System.Drawing.Color]::FromArgb(255, 7, 24, 29)
    $panel.Tag = $Color
    $panel.Add_Paint({
        param($s, $e)
        $g = $e.Graphics
        $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
        $accent = if ($s.Tag -is [System.Drawing.Color]) {
            $s.Tag
        } else {
            [System.Drawing.Color]::FromArgb(255, 245, 184, 64)
        }
        $linePen = New-Object System.Drawing.Pen(
            [System.Drawing.Color]::FromArgb(95, $accent.R, $accent.G, $accent.B), 1
        )
        $linePen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
        $linePen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
        $g.DrawLine($linePen, 28, 20, [Math]::Min($s.Width - 1, 150), 20)
        $linePen.Dispose()

        $dotBrush = New-Object System.Drawing.SolidBrush(
            [System.Drawing.Color]::FromArgb(125, $accent.R, $accent.G, $accent.B)
        )
        $g.FillEllipse($dotBrush, 154, 18, 3, 3)
        $dotBrush.Dispose()
    })

    $iconBox = New-Object System.Windows.Forms.PictureBox
    $iconBox.Location = New-Object System.Drawing.Point(0, 2)
    $iconBox.Size = New-Object System.Drawing.Size(18, 18)
    $iconBox.SizeMode = [System.Windows.Forms.PictureBoxSizeMode]::CenterImage
    $iconBox.BackColor = $panel.BackColor
    if (Get-Command New-ActionBitmap -ErrorAction SilentlyContinue) {
        $iconBox.Image = New-ActionBitmap -Action $Action -Color $Color
    }
    $panel.Controls.Add($iconBox)

    $label = New-Object System.Windows.Forms.Label
    $label.Text = $Text
    $label.Location = New-Object System.Drawing.Point(24, 2)
    $label.Size = New-Object System.Drawing.Size(300, 18)
    $label.ForeColor = $Color
    $label.BackColor = $panel.BackColor
    $label.Font = New-Object System.Drawing.Font("Segoe UI Semibold", 8.5, [System.Drawing.FontStyle]::Bold)
    $label.AutoEllipsis = $true
    $panel.Controls.Add($label)

    return $panel
}

function Clear-SettingsGeneratedImages {
    param([System.Windows.Forms.Control]$Root)
    if (-not $Root) { return }
    foreach ($child in @($Root.Controls)) {
        Clear-SettingsGeneratedImages -Root $child
    }
    if ($Root -is [System.Windows.Forms.PictureBox]) {
        $image = $Root.Image
        if ($image) {
            $Root.Image = $null
            try { $image.Dispose() } catch {}
        }
    }
    elseif ($Root -is [System.Windows.Forms.Button]) {
        $image = $Root.Image
        if ($image) {
            $Root.Image = $null
            try { $image.Dispose() } catch {}
        }
    }
}

function Set-SettingsPreviewPanelState {
    param(
        [System.Windows.Forms.Panel]$PreviewPanel,
        [System.Drawing.Color]$Color,
        [string]$State = "reminder"
    )

    if (-not $PreviewPanel) { return }
    $frame = 0
    if ($PreviewPanel.Tag -is [hashtable] -and $PreviewPanel.Tag.ContainsKey("Frame")) {
        $frame = [int]$PreviewPanel.Tag["Frame"]
    }
    $PreviewPanel.Tag = @{
        Accent = $Color
        State = if ([string]::IsNullOrWhiteSpace($State)) { "reminder" } else { "$State" }
        Frame = $frame
    }
    $PreviewPanel.Invalidate()
}

function Set-SettingsProfilePreview {
    param(
        [string]$ProfileId,
        [System.Collections.Specialized.OrderedDictionary]$Profiles,
        [System.Windows.Forms.Panel]$PreviewPanel,
        [System.Windows.Forms.PictureBox]$IconBox,
        [System.Windows.Forms.Label]$NameLabel,
        [System.Windows.Forms.Label]$MetaLabel,
        [System.Windows.Forms.Label]$NoteLabel,
        [hashtable]$Config = $null
    )

    if (-not $PreviewPanel -or -not $IconBox -or -not $NameLabel -or -not $MetaLabel -or -not $NoteLabel) {
        return
    }

    $oldImage = $IconBox.Image
    $IconBox.Image = $null
    if ($oldImage) {
        try { $oldImage.Dispose() } catch {}
    }

    $neutralColor = [System.Drawing.Color]::FromArgb(255, 245, 184, 64)
    if ([string]::IsNullOrWhiteSpace($ProfileId)) {
        Set-SettingsPreviewPanelState -PreviewPanel $PreviewPanel -Color $neutralColor -State "none"
        $NameLabel.Text = "No startup reminder profile"
        $MetaLabel.Text = "Tray starts without a suggested profile"
        $NoteLabel.Text = "No profile is applied automatically."
        if (Get-Command New-GameBitmap -ErrorAction SilentlyContinue) {
            $mark = New-GameBitmap -GameGroup "productivity" -Color $neutralColor -Category "Desktop"
            $IconBox.Image = New-SettingsPreviewMedallionBitmap -Mark $mark -Color $neutralColor
        }
        elseif (Get-Command New-ActionBitmap -ErrorAction SilentlyContinue) {
            $mark = New-ActionBitmap -Action "Startup" -Color $neutralColor
            $IconBox.Image = New-SettingsPreviewMedallionBitmap -Mark $mark -Color $neutralColor
        }
        return
    }

    if (-not $Profiles -or -not $Profiles.Contains($ProfileId)) {
        Set-SettingsPreviewPanelState -PreviewPanel $PreviewPanel -Color $neutralColor -State "missing"
        $missingName = Get-SettingsProfileDisplayName -ProfileId $ProfileId
        $gameGroup = Get-SettingsProfileGameGroup -ProfileId $ProfileId -Profile $null
        $modeBadge = Get-SettingsProfileModeBadge -ProfileId $ProfileId -Profile $null
        $NameLabel.Text = $missingName
        $MetaLabel.Text = "Not in the current profile list"
        $NoteLabel.Text = "Reminder is preserved; nothing is applied automatically."
        $mark = $null
        if (-not [string]::IsNullOrWhiteSpace($modeBadge) -and (Get-Command New-GameSyncBadgeBitmap -ErrorAction SilentlyContinue)) {
            $mark = New-GameSyncBadgeBitmap `
                -GameGroup $gameGroup `
                -Color $neutralColor `
                -Category "Other" `
                -SyncMode "agnostic" `
                -ModeBadge $modeBadge
        }
        elseif (Get-Command New-GameBitmap -ErrorAction SilentlyContinue) {
            $mark = New-GameBitmap -GameGroup $gameGroup -Color $neutralColor -Category "Other"
        }
        elseif (Get-Command New-ActionBitmap -ErrorAction SilentlyContinue) {
            $mark = New-ActionBitmap -Action "Startup" -Color $neutralColor
        }
        elseif (Get-Command New-CategoryBitmap -ErrorAction SilentlyContinue) {
            $mark = New-CategoryBitmap -Category "Other" -Color $neutralColor
        }
        if ($mark) {
            $IconBox.Image = New-SettingsPreviewMedallionBitmap -Mark $mark -Color $neutralColor -WarningBadge
        }
        return
    }

    $profile = $Profiles[$ProfileId]
    $cat = if ($profile.Cat) {
        if (Get-Command Format-TrayDisplayCopy -ErrorAction SilentlyContinue) {
            Format-TrayDisplayCopy -Text "$($profile.Cat)"
        }
        else {
            "$($profile.Cat)"
        }
    } else { "Other" }
    $catColor = if (Get-Command Get-CategoryColor -ErrorAction SilentlyContinue) {
        Get-CategoryColor -Category $cat -Fallback $neutralColor
    } else {
        $neutralColor
    }
    $gameGroup = Get-SettingsProfileGameGroup -ProfileId $ProfileId -Profile $profile

    $NameLabel.Text = if ($profile.Name) {
        if (Get-Command Format-TrayDisplayCopy -ErrorAction SilentlyContinue) {
            Format-TrayDisplayCopy -Text "$($profile.Name)"
        }
        else {
            "$($profile.Name)"
        }
    } else {
        if (Get-Command Format-TrayUserFacingText -ErrorAction SilentlyContinue) {
            Format-TrayUserFacingText -Text $ProfileId
        }
        else {
            "$ProfileId"
        }
    }
    $variant = if ($profile.Variant) { "$($profile.Variant)" } elseif ($profile.Sub) { "$($profile.Sub)" } else { $cat }
    if (Get-Command Format-TrayDisplayCopy -ErrorAction SilentlyContinue) {
        $variant = Format-TrayDisplayCopy -Text $variant
    }
    $MetaLabel.Text = "$variant  |  $cat"
    $NoteLabel.Text = "Startup reminder only. Nothing is applied automatically."
    $modeBadge = Get-SettingsProfileModeBadge -ProfileId $ProfileId -Profile $profile -Variant $variant
    $favoriteBadge = $false
    if ($Config -and $Config.ContainsKey("favorites")) {
        $favoriteBadge = (@($Config.favorites) | ForEach-Object { "$_" }) -contains "$ProfileId"
    }
    $previewState = if ($favoriteBadge) {
        "favorite"
    }
    elseif (-not [string]::IsNullOrWhiteSpace($modeBadge)) {
        "$modeBadge"
    }
    else {
        "reminder"
    }
    Set-SettingsPreviewPanelState -PreviewPanel $PreviewPanel -Color $catColor -State $previewState

    $mark = $null
    if ($favoriteBadge -and (Get-Command New-FavoriteGameBitmap -ErrorAction SilentlyContinue)) {
        $mark = New-FavoriteGameBitmap `
            -GameGroup $gameGroup `
            -Color $catColor `
            -Category $cat `
            -SyncMode "agnostic" `
            -ModeBadge $modeBadge
    }
    elseif (-not [string]::IsNullOrWhiteSpace($modeBadge) -and (Get-Command New-GameSyncBadgeBitmap -ErrorAction SilentlyContinue)) {
        $mark = New-GameSyncBadgeBitmap `
            -GameGroup $gameGroup `
            -Color $catColor `
            -Category $cat `
            -SyncMode "agnostic" `
            -ModeBadge $modeBadge
    }
    elseif (Get-Command New-GameBitmap -ErrorAction SilentlyContinue) {
        $mark = New-GameBitmap -GameGroup $gameGroup -Color $catColor -Category $cat
    }
    elseif (Get-Command New-CategoryBitmap -ErrorAction SilentlyContinue) {
        $mark = New-CategoryBitmap -Category $cat -Color $catColor
    }
    if ($mark) {
        $IconBox.Image = New-SettingsPreviewMedallionBitmap -Mark $mark -Color $catColor
    }
}

function Set-LastProfileState {
    <#
    .SYNOPSIS
    Persists the last known profile state for startup restore arbitration.
    #>
    param(
        [hashtable]$Config,
        [ValidateSet("active", "restored")]
        [string]$Status,
        [string]$ProfileId = $null,
        [string]$ProfileName = $null,
        [string]$Source = "tray",
        [string]$Timestamp = $null,
        [switch]$NoSave
    )

    if (-not $Config) { return $Config }

    $recordedAt = if ([string]::IsNullOrWhiteSpace($Timestamp)) {
        (Get-Date).ToString("o")
    }
    else {
        "$Timestamp"
    }

    $Config.lastProfileState = @{
        status    = $Status
        id        = if ($Status -eq "active") { $ProfileId } else { $null }
        name      = if ($Status -eq "active") { $ProfileName } else { $null }
        timestamp = $recordedAt
        source    = $Source
    }

    if (-not $NoSave) {
        Save-TrayConfig $Config
    }

    return $Config
}

function Set-StartupResolutionRecord {
    <#
    .SYNOPSIS
    Records the tray startup restore decision for later debugging.
    #>
    param(
        [hashtable]$Config,
        [object]$Record,
        [switch]$NoSave
    )

    if (-not $Config) { return $Config }

    if ($null -eq $Record) {
        $Config.lastStartupResolution = $null
    }
    else {
        $Config.lastStartupResolution = @{
            status         = if ($Record.status) { "$($Record.status)" } else { "status not reported" }
            id             = if ($Record.id) { "$($Record.id)" } else { $null }
            name           = if ($Record.name) { "$($Record.name)" } else { $null }
            timestamp      = if ($Record.timestamp) { "$($Record.timestamp)" } else { $null }
            source         = if ($Record.source) { "$($Record.source)" } else { "source not reported" }
            path           = if ($Record.path) { "$($Record.path)" } else { $null }
            decision       = if ($Record.decision) { "$($Record.decision)" } else { "decision not reported" }
            candidateCount = if ($null -ne $Record.candidate_count) { [int]$Record.candidate_count } else { 0 }
            resolvedAt     = (Get-Date).ToString("o")
        }
    }

    if (-not $NoSave) {
        Save-TrayConfig $Config
    }

    return $Config
}

# ============================================================================
# FAVORITES
# ============================================================================

function Test-Favorite {
    <#
    .SYNOPSIS
    Checks if a profile ID is in the favorites list.
    #>
    param([string]$ProfileId, [hashtable]$Config)
    return ($Config.favorites -contains $ProfileId)
}

function Toggle-Favorite {
    <#
    .SYNOPSIS
    Adds or removes a profile from favorites.
    #>
    param([string]$ProfileId, [hashtable]$Config)

    if ($Config.favorites -contains $ProfileId) {
        $Config.favorites = @($Config.favorites | Where-Object { $_ -ne $ProfileId })
    }
    else {
        $Config.favorites = @($Config.favorites) + $ProfileId
    }
    Save-TrayConfig $Config
    return $Config
}

# ============================================================================
# PROFILE HISTORY
# ============================================================================

function Add-ProfileHistory {
    <#
    .SYNOPSIS
    Records a profile application in history.
    #>
    param([string]$ProfileId, [string]$ProfileName, [hashtable]$Config)

    $displayTimestamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    $recordedAt = (Get-Date).ToString("o")
    $entry = @{
        id        = $ProfileId
        name      = $ProfileName
        timestamp = $displayTimestamp
        recorded_at = $recordedAt
        source    = "tray_apply"
    }

    # Add to recent (max 10)
    $recent = @($Config.recentProfiles)
    # Remove duplicates of same profile
    $recent = @($recent | Where-Object { $_.id -ne $ProfileId })
    $recent = @($entry) + $recent
    if ($recent.Count -gt 10) {
        $recent = $recent[0..9]
    }
    $Config.recentProfiles = $recent

    # Add to full history (max 50)
    $history = @($Config.profileHistory)
    $history = @($entry) + $history
    if ($history.Count -gt 50) {
        $history = $history[0..49]
    }
    $Config.profileHistory = $history

    $Config = Set-LastProfileState `
        -Config $Config `
        -Status "active" `
        -ProfileId $ProfileId `
        -ProfileName $ProfileName `
        -Source "tray_apply" `
        -Timestamp $recordedAt `
        -NoSave

    Save-TrayConfig $Config
    return $Config
}

# ============================================================================
# SETTINGS PANEL
# ============================================================================

function Show-SettingsPanel {
    <#
    .SYNOPSIS
    Shows a floating settings window (non-modal).
    .PARAMETER Config
    The current config hashtable.
    .PARAMETER OnSave
    Scriptblock to call when settings are saved, receives updated config.
    #>
    param(
        [hashtable]$Config,
        [scriptblock]$OnSave
    )

    if ($script:SettingsForm -and -not $script:SettingsForm.IsDisposed) {
        $script:SettingsForm.BringToFront()
        return
    }

    $form = New-Object System.Windows.Forms.Form
    $form.Text = "computa Settings"
    $form.ClientSize = New-Object System.Drawing.Size(404, 760)
    $form.MinimumSize = New-Object System.Drawing.Size(420, 780)
    $form.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::FixedDialog
    $form.MaximizeBox = $false
    $form.StartPosition = [System.Windows.Forms.FormStartPosition]::CenterScreen
    $form.BackColor = [System.Drawing.Color]::FromArgb(255, 7, 24, 29)
    $form.ForeColor = [System.Drawing.Color]::FromArgb(255, 225, 244, 240)
    $form.Font = New-Object System.Drawing.Font("Segoe UI", 9)
    $form.TopMost = $true

    $settingsHeaderPulseTimer = $null
    $settingsPreviewPulseTimer = $null
    $y = 16

    $settingsHeader = New-SettingsBrandHeaderPanel `
        -Accent ([System.Drawing.Color]::FromArgb(255, 0, 245, 212)) `
        -ChipText (Get-SettingsHeaderChipText -Config $Config)
    $settingsHeader.Location = New-Object System.Drawing.Point(10, $y)
    $form.Controls.Add($settingsHeader)
    $settingsHeaderPulseTimer = New-Object System.Windows.Forms.Timer
    $settingsHeaderPulseTimer.Interval = 95
    $settingsHeaderPulseTimer.Tag = $settingsHeader
    $settingsHeaderPulseTimer.Add_Tick({
        try {
            $target = $this.Tag
            if (-not $target -or $target.IsDisposed) {
                $this.Stop()
                $this.Dispose()
                return
            }
            if ($target.Tag -is [hashtable]) {
                $target.Tag["Frame"] = ([int]$target.Tag["Frame"] + 1) % 120
            }
            $target.Invalidate()
        } catch {
            try { $this.Stop(); $this.Dispose() } catch {}
        }
    })
    $settingsHeaderPulseTimer.Start()
    $y += 80

    # --- Startup Reminder Section ---
    $genLabel = New-SettingsSectionHeaderPanel `
        -Text "STARTUP REMINDER" `
        -Action "Startup" `
        -Color ([System.Drawing.Color]::FromArgb(255, 245, 184, 64))
    $genLabel.Location = New-Object System.Drawing.Point(16, $y)
    $form.Controls.Add($genLabel)
    $y += 28

    # Default profile
    $defLabel = New-Object System.Windows.Forms.Label
    $defLabel.Text = "Default Profile (startup reminder):"
    $defLabel.Location = New-Object System.Drawing.Point(16, $y)
    $defLabel.AutoSize = $true
    $form.Controls.Add($defLabel)
    $y += 24

    $defCombo = New-Object System.Windows.Forms.ComboBox
    $defCombo.Location = New-Object System.Drawing.Point(16, $y)
    $defCombo.Size = New-Object System.Drawing.Size(350, 28)
    $defCombo.DropDownStyle = [System.Windows.Forms.ComboBoxStyle]::DropDownList
    $defCombo.BackColor = [System.Drawing.Color]::FromArgb(255, 13, 42, 50)
    $defCombo.ForeColor = [System.Drawing.Color]::FromArgb(255, 225, 244, 240)
    $defCombo.Items.Add("(None)") | Out-Null
    # Populate with available profiles
    if ($script:Profiles) {
        foreach ($id in $script:Profiles.Keys) {
            $p = $script:Profiles[$id]
            $profileName = Get-SettingsProfileDisplayName -ProfileId $id -Profile $p
            $defCombo.Items.Add("$id - $profileName") | Out-Null
        }
    }
    # Select current default
    $defCombo.SelectedIndex = 0
    if ($Config.defaultProfile) {
        $matchedDefaultProfile = $false
        for ($i = 1; $i -lt $defCombo.Items.Count; $i++) {
            if ($defCombo.Items[$i].ToString().StartsWith("$($Config.defaultProfile) -")) {
                $defCombo.SelectedIndex = $i
                $matchedDefaultProfile = $true
                break
            }
        }
        if (-not $matchedDefaultProfile) {
            $missingDefaultName = Get-SettingsProfileDisplayName -ProfileId "$($Config.defaultProfile)"
            $defCombo.Items.Add("$($Config.defaultProfile) - $missingDefaultName (missing from current profile list)") | Out-Null
            $defCombo.SelectedIndex = $defCombo.Items.Count - 1
        }
    }
    $form.Controls.Add($defCombo)
    $y += 36

    $profilePreview = New-Object System.Windows.Forms.Panel
    $profilePreview.Location = New-Object System.Drawing.Point(16, $y)
    $profilePreview.Size = New-Object System.Drawing.Size(350, 66)
    $profilePreview.BackColor = [System.Drawing.Color]::FromArgb(255, 13, 42, 50)
    $profilePreview.Tag = @{
        Accent = [System.Drawing.Color]::FromArgb(255, 245, 184, 64)
        State = "none"
        Frame = 0
    }
    $profilePreview.Add_Paint({
        param($s, $e)
        $g = $e.Graphics
        $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
        $previewState = if ($s.Tag -is [hashtable]) { $s.Tag } else { @{} }
        $accent = if ($previewState.ContainsKey("Accent") -and $previewState["Accent"] -is [System.Drawing.Color]) {
            $previewState["Accent"]
        }
        elseif ($s.Tag -is [System.Drawing.Color]) {
            $s.Tag
        }
        else {
            [System.Drawing.Color]::FromArgb(255, 245, 184, 64)
        }
        $stateName = if ($previewState.ContainsKey("State")) { "$($previewState["State"])" } else { "reminder" }
        $frame = if ($previewState.ContainsKey("Frame")) { [int]$previewState["Frame"] } else { 0 }
        $stateColor = switch ($stateName) {
            "missing" { [System.Drawing.Color]::FromArgb(255, 245, 120, 92) }
            "favorite" { [System.Drawing.Color]::FromArgb(255, 245, 184, 64) }
            "capture" { [System.Drawing.Color]::FromArgb(255, 96, 180, 255) }
            "hdr" { [System.Drawing.Color]::FromArgb(255, 245, 184, 64) }
            "none" { [System.Drawing.Color]::FromArgb(255, 148, 183, 182) }
            default { $accent }
        }
        $barBrush = New-Object System.Drawing.SolidBrush($accent)
        $g.FillRectangle($barBrush, 0, 0, 4, $s.Height)
        $barBrush.Dispose()

        $railX = $s.Width - 9
        $railTop = 8
        $railHeight = $s.Height - 16
        $railBack = New-Object System.Drawing.SolidBrush(
            [System.Drawing.Color]::FromArgb(38, $stateColor.R, $stateColor.G, $stateColor.B)
        )
        $g.FillRectangle($railBack, $railX, $railTop, 3, $railHeight)
        $railBack.Dispose()
        $railAlpha = if ($stateName -in @("reminder", "favorite", "capture", "hdr")) {
            [int](100 + (55 * ([Math]::Sin($frame / 5.0) + 1.0)))
        }
        elseif ($stateName -eq "missing") {
            180
        }
        else {
            92
        }
        $railBrush = New-Object System.Drawing.SolidBrush(
            [System.Drawing.Color]::FromArgb($railAlpha, $stateColor.R, $stateColor.G, $stateColor.B)
        )
        $g.FillRectangle($railBrush, $railX, $railTop, 3, $railHeight)
        $railBrush.Dispose()

        $tickPen = New-Object System.Drawing.Pen(
            [System.Drawing.Color]::FromArgb(95, $stateColor.R, $stateColor.G, $stateColor.B), 1
        )
        for ($tickY = $railTop; $tickY -lt ($railTop + $railHeight); $tickY += 8) {
            $g.DrawLine($tickPen, ($railX - 3), $tickY, ($railX - 1), $tickY)
        }
        $tickPen.Dispose()

        if ($stateName -in @("reminder", "favorite", "capture", "hdr")) {
            $scanY = $railTop + (($frame * 3) % [Math]::Max(1, $railHeight))
            $scanPen = New-Object System.Drawing.Pen(
                [System.Drawing.Color]::FromArgb(220, 0, 245, 212), 1.2
            )
            $scanPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
            $scanPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
            $g.DrawLine($scanPen, ($railX - 4), $scanY, ($railX + 5), $scanY)
            $scanPen.Dispose()
        }

        $borderPen = New-Object System.Drawing.Pen(
            [System.Drawing.Color]::FromArgb(80, $accent.R, $accent.G, $accent.B), 1
        )
        $g.DrawRectangle($borderPen, 0, 0, ($s.Width - 1), ($s.Height - 1))
        $borderPen.Dispose()
    })

    $previewIcon = New-Object System.Windows.Forms.PictureBox
    $previewIcon.Location = New-Object System.Drawing.Point(14, 16)
    $previewIcon.Size = New-Object System.Drawing.Size(32, 32)
    $previewIcon.SizeMode = [System.Windows.Forms.PictureBoxSizeMode]::Zoom
    $previewIcon.BackColor = $profilePreview.BackColor
    $profilePreview.Controls.Add($previewIcon)

    $previewName = New-Object System.Windows.Forms.Label
    $previewName.Location = New-Object System.Drawing.Point(56, 8)
    $previewName.Size = New-Object System.Drawing.Size(282, 18)
    $previewName.ForeColor = [System.Drawing.Color]::FromArgb(255, 225, 244, 240)
    $previewName.BackColor = $profilePreview.BackColor
    $previewName.Font = New-Object System.Drawing.Font("Segoe UI Semibold", 9)
    $previewName.AutoEllipsis = $true
    $profilePreview.Controls.Add($previewName)

    $previewMeta = New-Object System.Windows.Forms.Label
    $previewMeta.Location = New-Object System.Drawing.Point(56, 27)
    $previewMeta.Size = New-Object System.Drawing.Size(282, 16)
    $previewMeta.ForeColor = [System.Drawing.Color]::FromArgb(255, 148, 183, 182)
    $previewMeta.BackColor = $profilePreview.BackColor
    $previewMeta.Font = New-Object System.Drawing.Font("Consolas", 7.5)
    $previewMeta.AutoEllipsis = $true
    $profilePreview.Controls.Add($previewMeta)

    $previewNote = New-Object System.Windows.Forms.Label
    $previewNote.Location = New-Object System.Drawing.Point(56, 45)
    $previewNote.Size = New-Object System.Drawing.Size(282, 16)
    $previewNote.ForeColor = [System.Drawing.Color]::FromArgb(255, 236, 191, 108)
    $previewNote.BackColor = $profilePreview.BackColor
    $previewNote.Font = New-Object System.Drawing.Font("Segoe UI", 7.5)
    $previewNote.AutoEllipsis = $true
    $profilePreview.Controls.Add($previewNote)

    $form.Controls.Add($profilePreview)
    Set-SettingsProfilePreview `
        -ProfileId (Get-SelectedDefaultProfileId -ComboBox $defCombo) `
        -Profiles $script:Profiles `
        -PreviewPanel $profilePreview `
        -IconBox $previewIcon `
        -NameLabel $previewName `
        -MetaLabel $previewMeta `
        -NoteLabel $previewNote `
        -Config $Config
    $settingsPreviewPulseTimer = New-Object System.Windows.Forms.Timer
    $settingsPreviewPulseTimer.Interval = 110
    $settingsPreviewPulseTimer.Tag = $profilePreview
    $settingsPreviewPulseTimer.Add_Tick({
        try {
            $target = $this.Tag
            if (-not $target -or $target.IsDisposed) {
                $this.Stop()
                $this.Dispose()
                return
            }
            if ($target.Tag -is [hashtable]) {
                $target.Tag["Frame"] = ([int]$target.Tag["Frame"] + 1) % 120
            }
            $target.Invalidate()
        } catch {
            try { $this.Stop(); $this.Dispose() } catch {}
        }
    })
    $settingsPreviewPulseTimer.Start()
    $defCombo.Add_SelectedIndexChanged({
        Set-SettingsProfilePreview `
            -ProfileId (Get-SelectedDefaultProfileId -ComboBox $defCombo) `
            -Profiles $script:Profiles `
            -PreviewPanel $profilePreview `
            -IconBox $previewIcon `
            -NameLabel $previewName `
            -MetaLabel $previewMeta `
            -NoteLabel $previewNote `
            -Config $Config
    })
    $y += 78

    # Gradient separator (gold gradient line)
    $sep1 = New-Object System.Windows.Forms.Panel
    $sep1.Location = New-Object System.Drawing.Point(16, $y)
    $sep1.Size = New-Object System.Drawing.Size(350, 3)
    $sep1.BackColor = [System.Drawing.Color]::Transparent
    $sep1.Add_Paint({
        param($s, $e)
        $sg = $e.Graphics
        $goldColor = [System.Drawing.Color]::FromArgb(255, 245, 184, 64)
        $gradBrush = New-Object System.Drawing.Drawing2D.LinearGradientBrush(
            (New-Object System.Drawing.Point(0, 1)),
            (New-Object System.Drawing.Point($s.Width, 1)),
            [System.Drawing.Color]::FromArgb(0, $goldColor.R, $goldColor.G, $goldColor.B),
            [System.Drawing.Color]::FromArgb(0, $goldColor.R, $goldColor.G, $goldColor.B)
        )
        $blend = New-Object System.Drawing.Drawing2D.ColorBlend(3)
        $blend.Colors = @(
            [System.Drawing.Color]::FromArgb(0, $goldColor.R, $goldColor.G, $goldColor.B),
            [System.Drawing.Color]::FromArgb(80, $goldColor.R, $goldColor.G, $goldColor.B),
            [System.Drawing.Color]::FromArgb(0, $goldColor.R, $goldColor.G, $goldColor.B)
        )
        $blend.Positions = @([float]0, [float]0.5, [float]1)
        $gradBrush.InterpolationColors = $blend
        $gradPen = New-Object System.Drawing.Pen($gradBrush, 1)
        $sg.DrawLine($gradPen, 0, 1, $s.Width, 1)
        $gradPen.Dispose()
        $gradBrush.Dispose()
    })
    $form.Controls.Add($sep1)
    $y += 12

    # --- Tray Surfaces Section ---
    $surfaceLabel = New-SettingsSectionHeaderPanel `
        -Text "TRAY SURFACES" `
        -Action "QuickPanel" `
        -Color ([System.Drawing.Color]::FromArgb(255, 0, 245, 212))
    $surfaceLabel.Location = New-Object System.Drawing.Point(16, $y)
    $form.Controls.Add($surfaceLabel)
    $y += 28

    $toastCheck = New-Object System.Windows.Forms.CheckBox
    $toastCheck.Text = "Show themed toast popups"
    $toastCheck.Checked = [bool]$Config.notificationsEnabled
    $toastCheck.Location = New-Object System.Drawing.Point(16, $y)
    $toastCheck.ForeColor = [System.Drawing.Color]::FromArgb(255, 210, 228, 225)
    $toastCheck.AutoSize = $true
    $form.Controls.Add($toastCheck)
    $y += 23

    $toastNote = New-Object System.Windows.Forms.Label
    $toastNote.Text = "Tray hover/status text still updates when popups are off."
    $toastNote.Location = New-Object System.Drawing.Point(36, $y)
    $toastNote.Size = New-Object System.Drawing.Size(330, 16)
    $toastNote.ForeColor = [System.Drawing.Color]::FromArgb(255, 148, 183, 182)
    $toastNote.Font = New-Object System.Drawing.Font("Segoe UI", 7.5)
    $toastNote.AutoEllipsis = $true
    $form.Controls.Add($toastNote)
    $y += 24

    $quickPanelCheck = New-Object System.Windows.Forms.CheckBox
    $quickPanelCheck.Text = "Restore Quick Panel on tray startup"
    $quickPanelCheck.Checked = [bool]$Config.showQuickPanel
    $quickPanelCheck.Location = New-Object System.Drawing.Point(16, $y)
    $quickPanelCheck.ForeColor = [System.Drawing.Color]::FromArgb(255, 210, 228, 225)
    $quickPanelCheck.AutoSize = $true
    $form.Controls.Add($quickPanelCheck)
    $y += 23

    $quickPanelNote = New-Object System.Windows.Forms.Label
    $quickPanelNote.Text = "Shows an empty/profile-missing card instead of silently hiding."
    $quickPanelNote.Location = New-Object System.Drawing.Point(36, $y)
    $quickPanelNote.Size = New-Object System.Drawing.Size(330, 16)
    $quickPanelNote.ForeColor = [System.Drawing.Color]::FromArgb(255, 148, 183, 182)
    $quickPanelNote.Font = New-Object System.Drawing.Font("Segoe UI", 7.5)
    $quickPanelNote.AutoEllipsis = $true
    $form.Controls.Add($quickPanelNote)
    $y += 30

    # --- Audio Section ---
    $audioLabel = New-SettingsSectionHeaderPanel `
        -Text "AUDIO" `
        -Action "Sound" `
        -Color ([System.Drawing.Color]::FromArgb(255, 245, 184, 64))
    $audioLabel.Location = New-Object System.Drawing.Point(16, $y)
    $form.Controls.Add($audioLabel)
    $y += 28

    $soundCheck = New-Object System.Windows.Forms.CheckBox
    $soundCheck.Text = "Enable tray audio cues"
    $soundCheck.Checked = $Config.soundEnabled
    $soundCheck.Location = New-Object System.Drawing.Point(16, $y)
    $soundCheck.ForeColor = [System.Drawing.Color]::FromArgb(255, 210, 228, 225)
    $soundCheck.AutoSize = $true
    $form.Controls.Add($soundCheck)
    $y += 28

    $volLabel = New-Object System.Windows.Forms.Label
    $volLabel.Text = "Volume:"
    $volLabel.Location = New-Object System.Drawing.Point(16, ($y + 2))
    $volLabel.AutoSize = $true
    $form.Controls.Add($volLabel)

    $volTrack = New-Object System.Windows.Forms.TrackBar
    $volTrack.Location = New-Object System.Drawing.Point(80, $y)
    $volTrack.Size = New-Object System.Drawing.Size(200, 30)
    $volTrack.Minimum = 0
    $volTrack.Maximum = 100
    $volTrack.Value = [int]($Config.soundVolume * 100)
    $volTrack.TickFrequency = 25
    $volTrack.BackColor = [System.Drawing.Color]::FromArgb(255, 7, 24, 29)
    $form.Controls.Add($volTrack)

    $volValueLabel = New-Object System.Windows.Forms.Label
    $volValueLabel.Text = "$([int]($Config.soundVolume * 100))%"
    $volValueLabel.Location = New-Object System.Drawing.Point(290, ($y + 2))
    $volValueLabel.AutoSize = $true
    $form.Controls.Add($volValueLabel)

    $volTrack.Add_ValueChanged({
        $volValueLabel.Text = "$($volTrack.Value)%"
    })
    $y += 48

    # Gradient separator (gold gradient line)
    $sep2 = New-Object System.Windows.Forms.Panel
    $sep2.Location = New-Object System.Drawing.Point(16, $y)
    $sep2.Size = New-Object System.Drawing.Size(350, 3)
    $sep2.BackColor = [System.Drawing.Color]::Transparent
    $sep2.Add_Paint({
        param($s, $e)
        $sg = $e.Graphics
        $goldColor = [System.Drawing.Color]::FromArgb(255, 245, 184, 64)
        $gradBrush = New-Object System.Drawing.Drawing2D.LinearGradientBrush(
            (New-Object System.Drawing.Point(0, 1)),
            (New-Object System.Drawing.Point($s.Width, 1)),
            [System.Drawing.Color]::FromArgb(0, $goldColor.R, $goldColor.G, $goldColor.B),
            [System.Drawing.Color]::FromArgb(0, $goldColor.R, $goldColor.G, $goldColor.B)
        )
        $blend = New-Object System.Drawing.Drawing2D.ColorBlend(3)
        $blend.Colors = @(
            [System.Drawing.Color]::FromArgb(0, $goldColor.R, $goldColor.G, $goldColor.B),
            [System.Drawing.Color]::FromArgb(80, $goldColor.R, $goldColor.G, $goldColor.B),
            [System.Drawing.Color]::FromArgb(0, $goldColor.R, $goldColor.G, $goldColor.B)
        )
        $blend.Positions = @([float]0, [float]0.5, [float]1)
        $gradBrush.InterpolationColors = $blend
        $gradPen = New-Object System.Drawing.Pen($gradBrush, 1)
        $sg.DrawLine($gradPen, 0, 1, $s.Width, 1)
        $gradPen.Dispose()
        $gradBrush.Dispose()
    })
    $form.Controls.Add($sep2)
    $y += 12

    # --- Hotkeys Section ---
    $hkLabel = New-SettingsSectionHeaderPanel `
        -Text "HOTKEYS" `
        -Action "Hotkey" `
        -Color ([System.Drawing.Color]::FromArgb(255, 245, 184, 64))
    $hkLabel.Location = New-Object System.Drawing.Point(16, $y)
    $form.Controls.Add($hkLabel)
    $y += 28

    $hk1Label = New-Object System.Windows.Forms.Label
    $hk1Label.Text = "Open Menu:"
    $hk1Label.Location = New-Object System.Drawing.Point(16, ($y + 4))
    $hk1Label.AutoSize = $true
    $form.Controls.Add($hk1Label)

    $hk1Text = New-Object System.Windows.Forms.TextBox
    $hk1Text.Text = $Config.hotkeys.openMenu
    $hk1Text.Location = New-Object System.Drawing.Point(120, $y)
    $hk1Text.Size = New-Object System.Drawing.Size(200, 26)
    $hk1Text.BackColor = [System.Drawing.Color]::FromArgb(255, 13, 42, 50)
    $hk1Text.ForeColor = [System.Drawing.Color]::FromArgb(255, 225, 244, 240)
    $hk1Text.ReadOnly = $true
    $form.Controls.Add($hk1Text)

    $hk1Status = New-HotkeyStatusChipLabel -Name "openMenu"
    $hk1Status.Location = New-Object System.Drawing.Point(326, ($y + 2))
    $form.Controls.Add($hk1Status)
    $y += 32

    $hk2Label = New-Object System.Windows.Forms.Label
    $hk2Label.Text = "Restore:"
    $hk2Label.Location = New-Object System.Drawing.Point(16, ($y + 4))
    $hk2Label.AutoSize = $true
    $form.Controls.Add($hk2Label)

    $hk2Text = New-Object System.Windows.Forms.TextBox
    $hk2Text.Text = $Config.hotkeys.restore
    $hk2Text.Location = New-Object System.Drawing.Point(120, $y)
    $hk2Text.Size = New-Object System.Drawing.Size(200, 26)
    $hk2Text.BackColor = [System.Drawing.Color]::FromArgb(255, 13, 42, 50)
    $hk2Text.ForeColor = [System.Drawing.Color]::FromArgb(255, 225, 244, 240)
    $hk2Text.ReadOnly = $true
    $form.Controls.Add($hk2Text)

    $hk2Status = New-HotkeyStatusChipLabel -Name "restore"
    $hk2Status.Location = New-Object System.Drawing.Point(326, ($y + 2))
    $form.Controls.Add($hk2Status)
    $y += 32

    $hkNote = New-Object System.Windows.Forms.Label
    $hkNote.Text = "Restore hotkey requires an active profile."
    $hkNote.Location = New-Object System.Drawing.Point(120, $y)
    $hkNote.Size = New-Object System.Drawing.Size(246, 16)
    $hkNote.ForeColor = [System.Drawing.Color]::FromArgb(255, 148, 183, 182)
    $hkNote.Font = New-Object System.Drawing.Font("Segoe UI", 7.5)
    $hkNote.AutoEllipsis = $true
    $form.Controls.Add($hkNote)
    $y += 32

    # --- Open Profiles Folder ---
    $profilesFolderBtn = New-Object System.Windows.Forms.Button
    $profilesFolderBtn.Text = "Open Profiles Folder"
    $profilesFolderBtn.Location = New-Object System.Drawing.Point(16, ($y + 10))
    $profilesFolderBtn.Size = New-Object System.Drawing.Size(180, 34)
    $profilesFolderBtn.BackColor = [System.Drawing.Color]::FromArgb(255, 16, 52, 60)
    $profilesFolderBtn.ForeColor = [System.Drawing.Color]::FromArgb(255, 155, 180, 178)
    $profilesFolderBtn.FlatStyle = [System.Windows.Forms.FlatStyle]::Flat
    $profilesFolderBtn.FlatAppearance.BorderSize = 0
    $profilesFolderBtn.Font = New-Object System.Drawing.Font("Segoe UI", 9)
    $profilesFolderBtn.Cursor = [System.Windows.Forms.Cursors]::Hand
    if (Get-Command New-ActionBitmap -ErrorAction SilentlyContinue) {
        $profilesFolderBtn.Image = New-ActionBitmap -Action "Folder" -Color ([System.Drawing.Color]::FromArgb(255, 155, 180, 178))
        $profilesFolderBtn.ImageAlign = [System.Drawing.ContentAlignment]::MiddleLeft
        $profilesFolderBtn.TextImageRelation = [System.Windows.Forms.TextImageRelation]::ImageBeforeText
        $profilesFolderBtn.Padding = New-Object System.Windows.Forms.Padding(8, 0, 8, 0)
    }
    $profilesFolderBtn.Add_Click({
        $profilesDir = Join-Path $env:USERPROFILE ".abso\profiles"
        if (-not (Test-Path $profilesDir)) {
            New-Item -ItemType Directory -Path $profilesDir -Force | Out-Null
        }
        Start-Process "explorer.exe" -ArgumentList $profilesDir
    })
    $form.Controls.Add($profilesFolderBtn)
    $y += 48

    # --- Save / Close Buttons ---
    $saveBtn = New-Object System.Windows.Forms.Button
    $saveBtn.Text = "Save"
    $saveBtn.Location = New-Object System.Drawing.Point(210, ($y + 10))
    $saveBtn.Size = New-Object System.Drawing.Size(90, 34)
    $saveBtn.BackColor = [System.Drawing.Color]::FromArgb(255, 70, 190, 110)
    $saveBtn.ForeColor = [System.Drawing.Color]::FromArgb(255, 16, 16, 16)
    $saveBtn.FlatStyle = [System.Windows.Forms.FlatStyle]::Flat
    $saveBtn.FlatAppearance.BorderSize = 0
    $saveBtn.Font = New-Object System.Drawing.Font("Segoe UI Semibold", 9)
    $saveBtn.Cursor = [System.Windows.Forms.Cursors]::Hand
    if (Get-Command New-ActionBitmap -ErrorAction SilentlyContinue) {
        $saveBtn.Image = New-ActionBitmap -Action "Save" -Color ([System.Drawing.Color]::FromArgb(255, 16, 16, 16))
        $saveBtn.ImageAlign = [System.Drawing.ContentAlignment]::MiddleLeft
        $saveBtn.TextImageRelation = [System.Windows.Forms.TextImageRelation]::ImageBeforeText
        $saveBtn.Padding = New-Object System.Windows.Forms.Padding(8, 0, 6, 0)
    }
    $saveBtn.Add_Click({
        $Config.soundEnabled = $soundCheck.Checked
        $Config.soundVolume = $volTrack.Value / 100.0
        $Config.notificationsEnabled = $toastCheck.Checked
        $Config.showQuickPanel = $quickPanelCheck.Checked
        # Save default profile selection
        if ($defCombo.SelectedIndex -le 0) {
            $Config.defaultProfile = $null
        } else {
            $Config.defaultProfile = Get-SelectedDefaultProfileId -ComboBox $defCombo
        }
        Save-TrayConfig $Config
        if ($OnSave) { & $OnSave $Config }
        $form.Close()
    })
    $form.Controls.Add($saveBtn)

    $closeBtn = New-Object System.Windows.Forms.Button
    $closeBtn.Text = "Close"
    $closeBtn.Location = New-Object System.Drawing.Point(310, ($y + 10))
    $closeBtn.Size = New-Object System.Drawing.Size(90, 34)
    $closeBtn.BackColor = [System.Drawing.Color]::FromArgb(255, 16, 52, 60)
    $closeBtn.ForeColor = [System.Drawing.Color]::FromArgb(255, 155, 180, 178)
    $closeBtn.FlatStyle = [System.Windows.Forms.FlatStyle]::Flat
    $closeBtn.FlatAppearance.BorderSize = 0
    $closeBtn.Font = New-Object System.Drawing.Font("Segoe UI", 9)
    $closeBtn.Cursor = [System.Windows.Forms.Cursors]::Hand
    if (Get-Command New-ActionBitmap -ErrorAction SilentlyContinue) {
        $closeBtn.Image = New-ActionBitmap -Action "Close" -Color ([System.Drawing.Color]::FromArgb(255, 155, 180, 178))
        $closeBtn.ImageAlign = [System.Drawing.ContentAlignment]::MiddleLeft
        $closeBtn.TextImageRelation = [System.Windows.Forms.TextImageRelation]::ImageBeforeText
        $closeBtn.Padding = New-Object System.Windows.Forms.Padding(8, 0, 6, 0)
    }
    $closeBtn.Add_Click({ $form.Close() })
    $form.Controls.Add($closeBtn)

    $requiredClientHeight = [Math]::Max(
        $profilesFolderBtn.Bottom,
        [Math]::Max($saveBtn.Bottom, $closeBtn.Bottom)
    ) + 16
    if ($form.ClientSize.Height -lt $requiredClientHeight) {
        $form.ClientSize = New-Object System.Drawing.Size($form.ClientSize.Width, $requiredClientHeight)
    }

    $script:SettingsForm = $form
    $form.Add_FormClosed({
        if ($settingsHeaderPulseTimer) {
            try { $settingsHeaderPulseTimer.Stop() } catch {}
            try { $settingsHeaderPulseTimer.Dispose() } catch {}
        }
        if ($settingsPreviewPulseTimer) {
            try { $settingsPreviewPulseTimer.Stop() } catch {}
            try { $settingsPreviewPulseTimer.Dispose() } catch {}
        }
        Clear-SettingsGeneratedImages -Root $form
        $form.Dispose()
        $script:SettingsForm = $null
    })
    $form.Show()

    # Apply full DWM effects (rounded corners, dark mode, shadow, border color)
    try {
        if (Get-Command Apply-DwmWindowEffects -ErrorAction SilentlyContinue) {
            Apply-DwmWindowEffects -Form $form -CornerStyle 2 -BorderColorRGB @(230, 190, 70)
        }
        elseif ("DwmHelper" -as [type]) {
            [DwmHelper]::SetDarkMode($form.Handle)
            $colorRef = 70 -shl 16 -bor 190 -shl 8 -bor 230
            [DwmHelper]::SetBorderColor($form.Handle, $colorRef)
        }
    } catch {}
}

# ============================================================================
# GLOBAL HOTKEYS (Win32 API)
# ============================================================================

$script:HotkeysRegistered = $false
$script:HotkeyActions = @{}
$script:HotkeyRegistrationStatus = @{}

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;

public class HotkeyHelper {
    [DllImport("user32.dll")]
    public static extern bool RegisterHotKey(IntPtr hWnd, int id, uint fsModifiers, uint vk);

    [DllImport("user32.dll")]
    public static extern bool UnregisterHotKey(IntPtr hWnd, int id);

    public const uint MOD_ALT = 0x0001;
    public const uint MOD_CONTROL = 0x0002;
    public const uint MOD_SHIFT = 0x0004;
    public const uint MOD_WIN = 0x0008;
    public const uint MOD_NOREPEAT = 0x4000;
}
"@ -ErrorAction SilentlyContinue

function Parse-HotkeyString {
    <#
    .SYNOPSIS
    Parses a hotkey string like "Ctrl+Shift+A" into modifier flags and virtual key code.
    #>
    param([string]$HotkeyStr)

    $parts = $HotkeyStr -split '\+'
    $modifiers = [uint32]0
    $vk = [uint32]0

    foreach ($part in $parts) {
        $p = $part.Trim()
        switch ($p.ToLower()) {
            "ctrl"  { $modifiers = $modifiers -bor 0x0002 }
            "alt"   { $modifiers = $modifiers -bor 0x0001 }
            "shift" { $modifiers = $modifiers -bor 0x0004 }
            "win"   { $modifiers = $modifiers -bor 0x0008 }
            default {
                if ($p.Length -eq 1) {
                    $vk = [uint32][char]$p.ToUpper()
                }
                elseif ($p -match '^F(\d+)$') {
                    $vk = [uint32](0x70 + [int]$Matches[1] - 1)
                }
                elseif ($p -match '^\d$') {
                    $vk = [uint32][char]$p
                }
            }
        }
    }

    # Add MOD_NOREPEAT
    $modifiers = $modifiers -bor 0x4000

    return @{ Modifiers = $modifiers; VK = $vk }
}

function Get-HotkeyConfigNames {
    param([hashtable]$Config)

    $names = @()
    if ($Config -and $Config.hotkeys) {
        if ($Config.hotkeys -is [hashtable]) {
            $names = @($Config.hotkeys.Keys)
        }
        else {
            $names = @($Config.hotkeys.PSObject.Properties.Name)
        }
    }

    $orderedNames = [System.Collections.Generic.List[string]]::new()
    foreach ($knownName in @("openMenu", "restore")) {
        if ($names -contains $knownName) {
            [void]$orderedNames.Add($knownName)
        }
    }
    foreach ($name in ($names | Sort-Object)) {
        if (-not $orderedNames.Contains($name)) {
            [void]$orderedNames.Add($name)
        }
    }
    return $orderedNames.ToArray()
}

function Get-HotkeyConfigValue {
    param(
        [hashtable]$Config,
        [string]$Name
    )

    if (-not $Config -or -not $Config.hotkeys -or [string]::IsNullOrWhiteSpace($Name)) {
        return $null
    }
    if ($Config.hotkeys -is [hashtable]) {
        if ($Config.hotkeys.ContainsKey($Name)) {
            return "$($Config.hotkeys[$Name])"
        }
        return $null
    }
    if ($Config.hotkeys.PSObject.Properties[$Name]) {
        return "$($Config.hotkeys.$Name)"
    }
    return $null
}

function Get-HotkeyActionDisplayName {
    param([string]$Name)

    switch ($Name) {
        "openMenu" { return "Open Menu" }
        "restore" { return "Restore Previous Settings" }
        default {
            if ([string]::IsNullOrWhiteSpace($Name)) {
                return "Action not reported"
            }
            return $Name
        }
    }
}

function Set-HotkeyRegistrationStatus {
    param(
        [string]$Name,
        [string]$Hotkey,
        [bool]$Active,
        [string]$Reason
    )

    if ([string]::IsNullOrWhiteSpace($Name)) { return }
    $script:HotkeyRegistrationStatus[$Name] = @{
        Hotkey = $Hotkey
        Active = $Active
        Reason = $Reason
    }
}

function Get-HotkeyRegistrationSummaryText {
    param([hashtable]$Config)

    $lines = [System.Collections.Generic.List[string]]::new()
    foreach ($name in (Get-HotkeyConfigNames -Config $Config)) {
        $hotkey = Get-HotkeyConfigValue -Config $Config -Name $name
        $actionName = Get-HotkeyActionDisplayName -Name $name
        $restoreContext = if ($name -eq "restore") { "; requires active profile" } else { "" }

        if ([string]::IsNullOrWhiteSpace($hotkey)) {
            [void]$lines.Add("${actionName}: not configured")
            continue
        }

        if ($script:HotkeyRegistrationStatus.ContainsKey($name)) {
            $status = $script:HotkeyRegistrationStatus[$name]
            if ($status.Active) {
                [void]$lines.Add("$hotkey - $actionName (active$restoreContext)")
            }
            else {
                $reason = if ([string]::IsNullOrWhiteSpace($status.Reason)) { "reason not reported" } else { "$($status.Reason)" }
                [void]$lines.Add("$hotkey - $actionName (unavailable: $reason$restoreContext)")
            }
        }
        else {
            [void]$lines.Add("$hotkey - $actionName (not registered this session$restoreContext)")
        }
    }

    if ($lines.Count -le 0) {
        return "Hotkeys:`n  Not configured"
    }
    return "Hotkeys:`n  $($lines -join "`n  ")"
}

function Get-HotkeyRegistrationChipInfo {
    param([string]$Name)

    if ([string]::IsNullOrWhiteSpace($Name)) {
        return [pscustomobject]@{
            Text      = "UNKNOWN"
            BackColor = [System.Drawing.Color]::FromArgb(255, 16, 52, 60)
            ForeColor = [System.Drawing.Color]::FromArgb(255, 185, 185, 195)
        }
    }

    if (-not $script:HotkeyRegistrationStatus.ContainsKey($Name)) {
        return [pscustomobject]@{
            Text      = "CONFIG"
            BackColor = [System.Drawing.Color]::FromArgb(255, 42, 46, 58)
            ForeColor = [System.Drawing.Color]::FromArgb(255, 185, 198, 215)
        }
    }

    $status = $script:HotkeyRegistrationStatus[$Name]
    if ($status.Active) {
        return [pscustomobject]@{
            Text      = "ACTIVE"
            BackColor = [System.Drawing.Color]::FromArgb(255, 18, 62, 58)
            ForeColor = [System.Drawing.Color]::FromArgb(255, 0, 245, 212)
        }
    }

    $reason = if ($status.Reason) { "$($status.Reason)" } else { "" }
    $text = switch -Regex ($reason) {
        "invalid" { "INVALID"; break }
        "not configured" { "EMPTY"; break }
        "no tray action" { "NO ACT"; break }
        default { "BLOCKED" }
    }

    return [pscustomobject]@{
        Text      = $text
        BackColor = [System.Drawing.Color]::FromArgb(255, 64, 45, 23)
        ForeColor = [System.Drawing.Color]::FromArgb(255, 245, 184, 64)
    }
}

function New-HotkeyStatusChipLabel {
    param([string]$Name)

    $chip = Get-HotkeyRegistrationChipInfo -Name $Name
    $label = New-Object System.Windows.Forms.Label
    $label.Text = $chip.Text
    $label.Size = New-Object System.Drawing.Size(68, 22)
    $label.BackColor = $chip.BackColor
    $label.ForeColor = $chip.ForeColor
    $label.Font = New-Object System.Drawing.Font("Segoe UI Semibold", 7)
    $label.TextAlign = [System.Drawing.ContentAlignment]::MiddleCenter
    $label.BorderStyle = [System.Windows.Forms.BorderStyle]::FixedSingle
    return $label
}

function Register-GlobalHotkeys {
    <#
    .SYNOPSIS
    Registers global hotkeys based on config.
    .PARAMETER WindowHandle
    The hidden form's window handle for receiving WM_HOTKEY.
    .PARAMETER Config
    Config hashtable with hotkeys section.
    .PARAMETER Actions
    Hashtable mapping hotkey names to scriptblocks.
    #>
    param(
        [IntPtr]$WindowHandle,
        [hashtable]$Config,
        [hashtable]$Actions
    )

    $script:HotkeyActions = @{}
    $script:HotkeyRegistrationStatus = @{}
    $script:HotkeysRegistered = $false

    $id = 1
    $configuredCount = 0
    foreach ($name in (Get-HotkeyConfigNames -Config $Config)) {
        $hkStr = Get-HotkeyConfigValue -Config $Config -Name $name
        if ([string]::IsNullOrWhiteSpace($hkStr)) {
            Set-HotkeyRegistrationStatus -Name $name -Hotkey $hkStr -Active $false -Reason "not configured"
            continue
        }

        $configuredCount++

        $parsed = Parse-HotkeyString $hkStr
        if ($parsed.VK -le 0) {
            Set-HotkeyRegistrationStatus -Name $name -Hotkey $hkStr -Active $false -Reason "invalid hotkey"
            $id++
            continue
        }
        if (-not $Actions -or -not $Actions.ContainsKey($name) -or -not $Actions[$name]) {
            Set-HotkeyRegistrationStatus -Name $name -Hotkey $hkStr -Active $false -Reason "no tray action"
            $id++
            continue
        }

        $result = $false
        try {
            $result = [HotkeyHelper]::RegisterHotKey($WindowHandle, $id, $parsed.Modifiers, $parsed.VK)
        }
        catch {
            Set-HotkeyRegistrationStatus -Name $name -Hotkey $hkStr -Active $false -Reason "registration error: $($_.Exception.Message)"
            $id++
            continue
        }

        if ($result) {
            $script:HotkeyActions[$id] = $Actions[$name]
            Set-HotkeyRegistrationStatus -Name $name -Hotkey $hkStr -Active $true -Reason "active"
        }
        else {
            Set-HotkeyRegistrationStatus -Name $name -Hotkey $hkStr -Active $false -Reason "Windows or another app is using it"
        }
        $id++
    }
    $script:HotkeysRegistered = ($script:HotkeyActions.Count -gt 0)

    return [pscustomobject]@{
        Total  = $configuredCount
        Active = $script:HotkeyActions.Count
        Failed = [Math]::Max(0, ($configuredCount - $script:HotkeyActions.Count))
    }
}

function Unregister-GlobalHotkeys {
    <#
    .SYNOPSIS
    Unregisters all global hotkeys.
    #>
    param([IntPtr]$WindowHandle)

    if ($script:HotkeysRegistered) {
        foreach ($id in $script:HotkeyActions.Keys) {
            [HotkeyHelper]::UnregisterHotKey($WindowHandle, $id) | Out-Null
        }
        $script:HotkeyActions = @{}
        $script:HotkeyRegistrationStatus = @{}
        $script:HotkeysRegistered = $false
    }
}

function Get-HotkeyAction {
    <#
    .SYNOPSIS
    Gets the action scriptblock for a hotkey ID.
    #>
    param([int]$HotkeyId)
    if ($script:HotkeyActions.ContainsKey($HotkeyId)) {
        return $script:HotkeyActions[$HotkeyId]
    }
    return $null
}
