# ABSO-Notifications.ps1 - v3.0 "Battle Station HUD" notifications
#
# Distinctive toast system for the A.B.S.O. tray. Replaces the generic
# dark-panel v2 design with a cockpit/telemetry aesthetic:
#
#   * Bahnschrift SemiBold Condensed titles (condensed DIN, Win10+)
#   * Cascadia Mono metadata row (Win11 native, falls back to Consolas)
#   * Phosphor HUD palette with sharp accents on cool neutral surfaces
#   * 2-char category badge block instead of generic status dot
#   * Segmented dismiss bar (HUD countdown), not smooth shrink
#   * Stacked queue (up to 3 visible, FIFO + Error priority, dedup window)
#   * Slide-in / slide-up motion signatures
#   * Low-alpha diagonal crosshatch background texture
#   * Per-toast isolated state (no single-slot stomp)
#
# Public API preserved: Show-ThemedToast, Close-ThemedToast,
# Show-ProgressOverlay, Update-ProgressOverlay, Close-ProgressOverlay,
# Show-ABSONotification, New-StatusBarItem.

# ============================================================================
# STATE
# ============================================================================

# Each active toast is a hashtable:
#   Form, TitleLabel, BodyLabel, MetaLabel, DismissBar, DismissBarTimer,
#   FadeTimer, LifetimeTimer, ReflowTimer, TargetY, CurrentY, Height,
#   CreatedAt, Accent, Key
$script:ActiveToasts      = [System.Collections.Generic.List[object]]::new()
$script:ToastQueue        = [System.Collections.Generic.Queue[object]]::new()
$script:ToastDedupMap     = @{}   # key -> last shown DateTime
$script:ToastMaxVisible   = 3
$script:ToastSlotGap      = 6
$script:ToastRightMargin  = 16
$script:ToastBottomMargin = 16
$script:ToastWidth        = 396
$script:ToastDedupWindowMs = 2000

# Font cache (resolve once with fallback chain)
$script:ToastFont_Title = $null
$script:ToastFont_Body  = $null
$script:ToastFont_Meta  = $null
$script:ToastFont_Badge = $null
$script:ToastFont_Close = $null

function _Resolve-ToastFont {
    param(
        [string[]]$Families,
        [float]$Size,
        [System.Drawing.FontStyle]$Style = [System.Drawing.FontStyle]::Regular
    )
    foreach ($family in $Families) {
        try {
            $f = New-Object System.Drawing.Font($family, $Size, $Style)
            # WinForms silently substitutes Microsoft Sans Serif when a family
            # is unknown; detect that and skip to the next candidate.
            if ($f.FontFamily.Name -ieq $family -or $f.FontFamily.Name -ieq ($family -split ' ')[0]) {
                return $f
            }
            # If substitution landed on the generic family, still accept if
            # the root family (e.g. "Bahnschrift") resolved.
            if ($f.Name -and $f.Name -ilike "$(($family -split ' ')[0])*") {
                return $f
            }
            $f.Dispose()
        } catch {}
    }
    # Last-resort: Segoe UI at the given size
    return New-Object System.Drawing.Font("Segoe UI", $Size, $Style)
}

function _Ensure-ToastFonts {
    if ($null -ne $script:ToastFont_Title) { return }
    $script:ToastFont_Title = _Resolve-ToastFont `
        -Families @("Bahnschrift SemiBold Condensed","Bahnschrift Condensed","Bahnschrift","Segoe UI Semibold") `
        -Size 13.0 -Style ([System.Drawing.FontStyle]::Bold)
    $script:ToastFont_Body  = _Resolve-ToastFont -Families @("Segoe UI") -Size 9.5
    $script:ToastFont_Meta  = _Resolve-ToastFont -Families @("Cascadia Mono","Consolas") -Size 8.0
    $script:ToastFont_Badge = _Resolve-ToastFont `
        -Families @("Bahnschrift SemiBold Condensed","Bahnschrift Condensed","Bahnschrift","Segoe UI Semibold") `
        -Size 10.5 -Style ([System.Drawing.FontStyle]::Bold)
    $script:ToastFont_Close = _Resolve-ToastFont -Families @("Segoe UI") -Size 11.0
}

# ============================================================================
# PALETTE / TYPE METADATA
# ============================================================================

function _Get-ToastTypeMeta {
    param([string]$Type)
    # Accent color + category badge tag. Cool HUD/phosphor palette.
    switch ($Type) {
        "Success" {
            return @{
                Accent    = [System.Drawing.Color]::FromArgb(255, 87, 255, 164)
                AccentDim = [System.Drawing.Color]::FromArgb(70, 87, 255, 164)
                Tag       = "OK"
                Priority  = 2
            }
        }
        "Warning" {
            return @{
                Accent    = [System.Drawing.Color]::FromArgb(255, 255, 181, 71)
                AccentDim = [System.Drawing.Color]::FromArgb(70, 255, 181, 71)
                Tag       = "!"
                Priority  = 3
            }
        }
        "Error" {
            return @{
                Accent    = [System.Drawing.Color]::FromArgb(255, 255, 77, 94)
                AccentDim = [System.Drawing.Color]::FromArgb(70, 255, 77, 94)
                Tag       = "X!"
                Priority  = 4
            }
        }
        default {
            return @{
                Accent    = [System.Drawing.Color]::FromArgb(255, 0, 212, 255)
                AccentDim = [System.Drawing.Color]::FromArgb(70, 0, 212, 255)
                Tag       = "i"
                Priority  = 1
            }
        }
    }
}

# ============================================================================
# SMART TITLE / METADATA DERIVATION
# ============================================================================

function _Derive-ToastTitle {
    param([string]$RawTitle, [string]$Message, [string]$Type)
    # If caller gave us the generic brand-only title, synthesize a better one
    # from context instead of wasting the headline slot on "A.B.S.O.".
    $trim = "$RawTitle".Trim()
    $genericTitles = @("A.B.S.O.", "A.B.S.O", "ABSO", "")
    if ($genericTitles -notcontains $trim -and $trim -inotlike "A.B.S.O.*") {
        return $trim
    }
    if ($trim -ilike "A.B.S.O.*") {
        # Strip the brand prefix and keep the suffix ("A.B.S.O. Audit" -> "AUDIT")
        $suffix = ($trim -replace '^A\.B\.S\.O\.?\s*', '').Trim()
        if ($suffix) { return $suffix.ToUpper() }
    }
    # Synthesize from message: first sentence, capped, upper-cased.
    $msg = "$Message".Trim()
    if (-not $msg) {
        if ($Type -eq "Success") { return "COMPLETE" }
        elseif ($Type -eq "Warning") { return "HEADS UP" }
        elseif ($Type -eq "Error") { return "FAILURE" }
        else { return "STATUS" }
    }
    # Take the first clause up to the first punctuation break.
    $clause = ($msg -split '[.!?:|]',2)[0].Trim()
    if ($clause.Length -gt 42) { $clause = $clause.Substring(0, 42).Trim() + [char]0x2026 }
    return $clause.ToUpper()
}

function _Format-ToastMeta {
    param([string]$Meta)
    $time = (Get-Date).ToString("HH:mm:ss")
    if ($Meta) {
        return ("{0}  {1}  {2}" -f $time, [char]0x00B7, $Meta)
    }
    return $time
}

# ============================================================================
# SLOT LAYOUT
# ============================================================================

function _Compute-ToastTargetY {
    param([int]$IndexFromBottom, [int]$Height)
    $screen = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
    $yBottom = $screen.Bottom - $script:ToastBottomMargin
    # Sum heights of toasts below this slot (indexFromBottom == 0 means bottom slot)
    $accum = 0
    for ($i = 0; $i -lt $IndexFromBottom; $i++) {
        if ($i -lt $script:ActiveToasts.Count) {
            $accum += ($script:ActiveToasts[$i].Height + $script:ToastSlotGap)
        } else {
            $accum += ($Height + $script:ToastSlotGap)
        }
    }
    return ($yBottom - $Height - $accum)
}

function _Reflow-ToastStack {
    # Animate each active toast to its correct slot Y.
    for ($i = 0; $i -lt $script:ActiveToasts.Count; $i++) {
        $t = $script:ActiveToasts[$i]
        if (-not $t.Form -or $t.Form.IsDisposed) { continue }
        $targetY = _Compute-ToastTargetY -IndexFromBottom $i -Height $t.Height
        $t.TargetY = $targetY
        if ($t.ReflowTimer) {
            try { $t.ReflowTimer.Stop(); $t.ReflowTimer.Dispose() } catch {}
        }
        $timer = New-Object System.Windows.Forms.Timer
        $timer.Interval = 14
        $state = @{ Toast = $t; Timer = $timer }
        $timer.Add_Tick({
            try {
                $local = $this.Tag
                $tt = $local.Toast
                if (-not $tt.Form -or $tt.Form.IsDisposed) { $local.Timer.Stop(); $local.Timer.Dispose(); return }
                $diff = $tt.TargetY - $tt.CurrentY
                if ([Math]::Abs($diff) -le 1) {
                    $tt.CurrentY = $tt.TargetY
                    $tt.Form.Top = [int]$tt.TargetY
                    $local.Timer.Stop(); $local.Timer.Dispose()
                    return
                }
                $step = [Math]::Sign($diff) * [Math]::Max(1, [Math]::Ceiling([Math]::Abs($diff) * 0.28))
                $tt.CurrentY = $tt.CurrentY + $step
                $tt.Form.Top = [int]$tt.CurrentY
            } catch { try { $this.Stop(); $this.Dispose() } catch {} }
        })
        $timer.Tag = $state
        $t.ReflowTimer = $timer
        $timer.Start()
    }
}

# ============================================================================
# TEXTURE / PAINT HELPERS
# ============================================================================

function _Paint-ToastPanel {
    param(
        [System.Drawing.Graphics]$g,
        [int]$Width,
        [int]$Height,
        [hashtable]$Meta
    )
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias

    # Panel background with subtle cool gradient
    try {
        $panelBrush = New-Object System.Drawing.Drawing2D.LinearGradientBrush(
            (New-Object System.Drawing.Rectangle(0, 0, $Width, $Height)),
            [System.Drawing.Color]::FromArgb(255, 11, 13, 16),
            [System.Drawing.Color]::FromArgb(255, 15, 20, 26),
            [System.Drawing.Drawing2D.LinearGradientMode]::Vertical
        )
        $g.FillRectangle($panelBrush, 0, 0, $Width, $Height)
        $panelBrush.Dispose()
    } catch {}

    # Diagonal crosshatch texture (very low alpha)
    $hatchPen = New-Object System.Drawing.Pen(
        [System.Drawing.Color]::FromArgb(6, 255, 255, 255), 1
    )
    for ($x = -$Height; $x -lt $Width; $x += 7) {
        $g.DrawLine($hatchPen, $x, 0, ($x + $Height), $Height)
    }
    $hatchPen.Dispose()

    # Outer border (thin, accent-tinted)
    $borderPen = New-Object System.Drawing.Pen($Meta.AccentDim, 1)
    $g.DrawRectangle($borderPen, 0, 0, ($Width - 1), ($Height - 1))
    $borderPen.Dispose()

    # Top stripe with tick marks (HUD signature)
    $topBrush = New-Object System.Drawing.SolidBrush(
        [System.Drawing.Color]::FromArgb(220, $Meta.Accent.R, $Meta.Accent.G, $Meta.Accent.B)
    )
    $g.FillRectangle($topBrush, 0, 0, $Width, 2)
    $topBrush.Dispose()
    # Tick-mark breaks on top stripe
    $tickBrush = New-Object System.Drawing.SolidBrush(
        [System.Drawing.Color]::FromArgb(255, 11, 13, 16)
    )
    for ($tx = 44; $tx -lt $Width; $tx += 28) {
        $g.FillRectangle($tickBrush, $tx, 0, 1, 2)
    }
    $tickBrush.Dispose()

    # Left accent rail (vertical 3px)
    $railBrush = New-Object System.Drawing.SolidBrush(
        [System.Drawing.Color]::FromArgb(220, $Meta.Accent.R, $Meta.Accent.G, $Meta.Accent.B)
    )
    $g.FillRectangle($railBrush, 0, 2, 3, ($Height - 4))
    $railBrush.Dispose()

    # Badge block (solid accent block, 40x40, left-aligned below top stripe)
    $badgeBrush = New-Object System.Drawing.SolidBrush($Meta.Accent)
    $g.FillRectangle($badgeBrush, 6, 10, 40, 40)
    $badgeBrush.Dispose()

    # Badge inner shadow edge (subtle, to give depth)
    $shadowPen = New-Object System.Drawing.Pen(
        [System.Drawing.Color]::FromArgb(60, 0, 0, 0), 1
    )
    $g.DrawRectangle($shadowPen, 6, 10, 39, 39)
    $shadowPen.Dispose()

    # Badge tag text (rendered via label for font smoothing; see _Build-ToastForm)
}

# ============================================================================
# FORM CONSTRUCTION
# ============================================================================

function _Build-ToastForm {
    param(
        [string]$Title,
        [string]$Message,
        [string]$MetaText,
        [hashtable]$TypeMeta
    )
    _Ensure-ToastFonts

    # Measure message to size the form height. Body area width = total - 60 (badge col) - 14 (right margin).
    $bodyWidth = $script:ToastWidth - 62 - 14
    $msgLines = [Math]::Max(1, [Math]::Ceiling($Message.Length / 54.0))
    if ($msgLines -gt 3) { $msgLines = 3 }
    $bodyHeight = [Math]::Max(18, $msgLines * 16)
    $height = 24 + 22 + $bodyHeight + 18 + 6     # top stripe + title row + body + meta + bottom bar
    $height = [Math]::Max($height, 88)
    $height = [Math]::Min($height, 160)

    $form = New-Object System.Windows.Forms.Form
    $form.Text = ""
    $form.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::None
    $form.BackColor = [System.Drawing.Color]::FromArgb(255, 11, 13, 16)
    $form.Size = New-Object System.Drawing.Size($script:ToastWidth, $height)
    $form.StartPosition = [System.Windows.Forms.FormStartPosition]::Manual
    $form.TopMost = $true
    $form.ShowInTaskbar = $false
    $form.Opacity = 0

    # Captured for paint closure
    $capturedW = $script:ToastWidth
    $capturedH = $height
    $capturedMeta = $TypeMeta
    $form.Add_Paint({
        param($s, $e)
        _Paint-ToastPanel -g $e.Graphics -Width $capturedW -Height $capturedH -Meta $capturedMeta
    }.GetNewClosure())

    # Badge tag label (white text on accent block)
    $badgeLabel = New-Object System.Windows.Forms.Label
    $badgeLabel.Text = $TypeMeta.Tag
    $badgeLabel.Font = $script:ToastFont_Badge
    $badgeLabel.ForeColor = [System.Drawing.Color]::FromArgb(255, 11, 13, 16)
    $badgeLabel.BackColor = [System.Drawing.Color]::Transparent
    $badgeLabel.TextAlign = [System.Drawing.ContentAlignment]::MiddleCenter
    $badgeLabel.Location = New-Object System.Drawing.Point(6, 10)
    $badgeLabel.Size = New-Object System.Drawing.Size(40, 40)
    $form.Controls.Add($badgeLabel)

    # Title label (uppercase, condensed, bold)
    $titleLabel = New-Object System.Windows.Forms.Label
    $titleLabel.Text = $Title.ToUpper()
    $titleLabel.Font = $script:ToastFont_Title
    $titleLabel.ForeColor = [System.Drawing.Color]::FromArgb(255, 232, 236, 243)
    $titleLabel.BackColor = [System.Drawing.Color]::Transparent
    $titleLabel.Location = New-Object System.Drawing.Point(60, 8)
    $titleLabel.Size = New-Object System.Drawing.Size(($script:ToastWidth - 60 - 30), 22)
    $titleLabel.AutoEllipsis = $true
    $form.Controls.Add($titleLabel)

    # Close glyph (right-aligned)
    $closeLabel = New-Object System.Windows.Forms.Label
    $closeLabel.Text = [string][char]0x00D7   # multiplication sign as close glyph
    $closeLabel.Font = $script:ToastFont_Close
    $closeLabel.ForeColor = [System.Drawing.Color]::FromArgb(180, 120, 128, 140)
    $closeLabel.BackColor = [System.Drawing.Color]::Transparent
    $closeLabel.TextAlign = [System.Drawing.ContentAlignment]::MiddleCenter
    $closeLabel.Location = New-Object System.Drawing.Point(($script:ToastWidth - 24), 10)
    $closeLabel.Size = New-Object System.Drawing.Size(18, 18)
    $closeLabel.Cursor = [System.Windows.Forms.Cursors]::Hand
    $closeLabel.Add_MouseEnter({ $this.ForeColor = [System.Drawing.Color]::FromArgb(255, 232, 236, 243) })
    $closeLabel.Add_MouseLeave({ $this.ForeColor = [System.Drawing.Color]::FromArgb(180, 120, 128, 140) })
    $form.Controls.Add($closeLabel)

    # Body label
    $bodyLabel = New-Object System.Windows.Forms.Label
    $bodyLabel.Text = $Message
    $bodyLabel.Font = $script:ToastFont_Body
    $bodyLabel.ForeColor = [System.Drawing.Color]::FromArgb(255, 166, 171, 182)
    $bodyLabel.BackColor = [System.Drawing.Color]::Transparent
    $bodyLabel.Location = New-Object System.Drawing.Point(60, 32)
    $bodyLabel.Size = New-Object System.Drawing.Size($bodyWidth, $bodyHeight)
    $form.Controls.Add($bodyLabel)

    # Metadata label (monospaced, dim)
    $metaLabel = New-Object System.Windows.Forms.Label
    $metaLabel.Text = $MetaText
    $metaLabel.Font = $script:ToastFont_Meta
    $metaLabel.ForeColor = [System.Drawing.Color]::FromArgb(255, 96, 102, 111)
    $metaLabel.BackColor = [System.Drawing.Color]::Transparent
    $metaLabel.Location = New-Object System.Drawing.Point(60, ($height - 24))
    $metaLabel.Size = New-Object System.Drawing.Size(($script:ToastWidth - 60 - 14), 14)
    $form.Controls.Add($metaLabel)

    # Segmented dismiss bar (24 discrete blocks) along the bottom
    $dismissHost = New-Object System.Windows.Forms.Panel
    $dismissHost.Location = New-Object System.Drawing.Point(3, ($height - 3))
    $dismissHost.Size = New-Object System.Drawing.Size(($script:ToastWidth - 6), 3)
    $dismissHost.BackColor = [System.Drawing.Color]::FromArgb(255, 22, 26, 32)
    $form.Controls.Add($dismissHost)

    return @{
        Form        = $form
        TitleLabel  = $titleLabel
        BodyLabel   = $bodyLabel
        MetaLabel   = $metaLabel
        CloseLabel  = $closeLabel
        BadgeLabel  = $badgeLabel
        DismissHost = $dismissHost
        Height      = $height
    }
}

# ============================================================================
# PUBLIC: Show-ThemedToast
# ============================================================================

function Show-ThemedToast {
    <#
    .SYNOPSIS
    Shows a HUD-style notification. Supports stacking, queueing, dedup.

    .PARAMETER Title
    Toast headline. If the caller passes the generic "A.B.S.O." brand,
    a contextual title is synthesized from the message instead.

    .PARAMETER Message
    Body text.

    .PARAMETER Type
    Info | Success | Warning | Error

    .PARAMETER Duration
    Lifetime in milliseconds before auto-dismiss (default 4500).

    .PARAMETER MetaText
    Optional metadata for the bottom row (timestamp is always prepended).
    #>
    param(
        [string]$Title = "A.B.S.O.",
        [string]$Message = "",
        [ValidateSet("Info","Warning","Error","Success")]
        [string]$Type = "Info",
        [int]$Duration = 4500,
        [string]$MetaText = ""
    )

    try {
        $typeMeta  = _Get-ToastTypeMeta -Type $Type
        $realTitle = _Derive-ToastTitle -RawTitle $Title -Message $Message -Type $Type
        $meta      = _Format-ToastMeta -Meta $MetaText
        $key       = "$Type|$realTitle|$Message"

        # Dedup: if this exact key appeared within the dedup window, drop it
        $nowMs = [DateTimeOffset]::Now.ToUnixTimeMilliseconds()
        if ($script:ToastDedupMap.ContainsKey($key)) {
            $last = $script:ToastDedupMap[$key]
            if (($nowMs - $last) -lt $script:ToastDedupWindowMs) {
                if (Get-Command Write-TrayLog -ErrorAction SilentlyContinue) {
                    Write-TrayLog "Toast dedup: suppressed '$realTitle' within ${script:ToastDedupWindowMs}ms" -Level "INFO"
                }
                return
            }
        }
        $script:ToastDedupMap[$key] = $nowMs

        # Log every surfaced toast
        if (Get-Command Write-TrayLog -ErrorAction SilentlyContinue) {
            Write-TrayLog "Toast[$Type] $realTitle :: $Message" -Level "INFO"
        }

        # Enqueue if at capacity (unless this is an Error, which preempts
        # the oldest Info/Success to make sure critical signals surface).
        if ($script:ActiveToasts.Count -ge $script:ToastMaxVisible) {
            if ($typeMeta.Priority -ge 4) {
                $bumpIndex = -1
                for ($i = 0; $i -lt $script:ActiveToasts.Count; $i++) {
                    $p = (_Get-ToastTypeMeta -Type $script:ActiveToasts[$i].Type).Priority
                    if ($p -le 2) { $bumpIndex = $i; break }
                }
                if ($bumpIndex -ge 0) {
                    _Dismiss-ActiveToast -Toast $script:ActiveToasts[$bumpIndex] -Fast
                } else {
                    $script:ToastQueue.Enqueue(@{
                        Title = $realTitle; Message = $Message; Type = $Type
                        Duration = $Duration; MetaText = $MetaText
                    })
                    return
                }
            } else {
                $script:ToastQueue.Enqueue(@{
                    Title = $realTitle; Message = $Message; Type = $Type
                    Duration = $Duration; MetaText = $MetaText
                })
                return
            }
        }

        _Spawn-Toast -Title $realTitle -Message $Message -Type $Type `
            -TypeMeta $typeMeta -MetaText $meta -Duration $Duration -Key $key
    } catch {
        if (Get-Command Write-TrayLog -ErrorAction SilentlyContinue) {
            Write-TrayLog "Show-ThemedToast failed: $($_.Exception.Message)" -Level "ERROR"
        }
    }
}

function _Spawn-Toast {
    param(
        [string]$Title, [string]$Message, [string]$Type,
        [hashtable]$TypeMeta, [string]$MetaText, [int]$Duration, [string]$Key
    )

    $built = _Build-ToastForm -Title $Title -Message $Message -MetaText $MetaText -TypeMeta $TypeMeta
    $form = $built.Form

    # Slot index = ActiveToasts.Count (this toast will become the new bottom slot)
    $slotIndex = $script:ActiveToasts.Count
    $targetY = _Compute-ToastTargetY -IndexFromBottom $slotIndex -Height $built.Height

    # Slide-in start: 28px to the right of target, opacity 0
    $screen = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
    $targetX = $screen.Right - $script:ToastWidth - $script:ToastRightMargin
    $form.Location = New-Object System.Drawing.Point(($targetX + 28), $targetY)

    $toast = @{
        Form           = $form
        TitleLabel     = $built.TitleLabel
        BodyLabel      = $built.BodyLabel
        MetaLabel      = $built.MetaLabel
        CloseLabel     = $built.CloseLabel
        BadgeLabel     = $built.BadgeLabel
        DismissHost    = $built.DismissHost
        Height         = $built.Height
        CurrentY       = $targetY
        TargetY        = $targetY
        Accent         = $TypeMeta.Accent
        Type           = $Type
        Key            = $Key
        Duration       = $Duration
        CreatedAt      = Get-Date
        FadeTimer      = $null
        LifetimeTimer  = $null
        DismissBarTimer= $null
        ReflowTimer    = $null
        SlideTimer     = $null
        DismissRects   = @()   # holds the 24 segment rectangles
        Dismissing     = $false
    }

    # Click-anywhere-to-dismiss on form and text labels
    $closeHandler = { _Dismiss-ActiveToast -Toast $toast }.GetNewClosure()
    $form.Add_Click($closeHandler)
    $built.TitleLabel.Add_Click($closeHandler)
    $built.BodyLabel.Add_Click($closeHandler)
    $built.MetaLabel.Add_Click($closeHandler)
    $built.BadgeLabel.Add_Click($closeHandler)
    $built.CloseLabel.Add_Click($closeHandler)

    $form.Show()

    # DWM effects (rounded corners, dark mode, accent border)
    try {
        if ("DwmHelper" -as [type]) {
            Apply-DwmWindowEffects -Form $form -CornerStyle 3 -BorderColorRGB @(
                $TypeMeta.Accent.R, $TypeMeta.Accent.G, $TypeMeta.Accent.B
            )
        }
    } catch {}

    $script:ActiveToasts.Add($toast) | Out-Null

    # Kick off the entry animation (slide-in from +28 with fade)
    _Animate-ToastEntry -Toast $toast -TargetX $targetX

    # Segmented dismiss bar animation (24 blocks fill over duration)
    _Start-DismissBar -Toast $toast

    # Lifetime -> auto-dismiss
    $lt = New-Object System.Windows.Forms.Timer
    $lt.Interval = $Duration
    $lt.Tag = $toast
    $lt.Add_Tick({
        try {
            $this.Stop(); $this.Dispose()
            $t = $this.Tag
            if ($t -and -not $t.Dismissing) { _Dismiss-ActiveToast -Toast $t }
        } catch {}
    })
    $lt.Start()
    $toast.LifetimeTimer = $lt
}

# ============================================================================
# ANIMATION
# ============================================================================

function _Animate-ToastEntry {
    param([hashtable]$Toast, [int]$TargetX)
    $steps = 14        # ~14 * 14ms = 196ms
    $step  = [ref]0
    $timer = New-Object System.Windows.Forms.Timer
    $timer.Interval = 14
    $state = @{ Toast = $Toast; Step = $step; Steps = $steps; TargetX = $TargetX }
    $timer.Tag = $state
    $timer.Add_Tick({
        try {
            $local = $this.Tag
            $tt = $local.Toast
            if (-not $tt.Form -or $tt.Form.IsDisposed) { $this.Stop(); $this.Dispose(); return }
            $local.Step.Value++
            $raw = [double]$local.Step.Value / $local.Steps
            if ($raw -ge 1) { $raw = 1 }
            # Ease-out cubic
            $eased = 1 - [Math]::Pow(1 - $raw, 3)
            $x = [int]($local.TargetX + ((1 - $eased) * 28))
            $tt.Form.Left = $x
            $tt.Form.Opacity = [Math]::Min(0.97, $eased * 0.97 + 0.02)
            if ($raw -ge 1) { $this.Stop(); $this.Dispose() }
        } catch { try { $this.Stop(); $this.Dispose() } catch {} }
    })
    $Toast.SlideTimer = $timer
    $timer.Start()
}

function _Start-DismissBar {
    param([hashtable]$Toast)
    # Pre-build 24 small panels; reveal them one at a time.
    # (Local name is $barHost -- $host is a read-only automatic in PS.)
    $barHost = $Toast.DismissHost
    $total = 24
    $width = $barHost.Width
    $segW = [Math]::Max(1, [Math]::Floor(($width - ($total - 1) * 1) / $total))
    $rects = @()
    for ($i = 0; $i -lt $total; $i++) {
        $seg = New-Object System.Windows.Forms.Panel
        $seg.Size = New-Object System.Drawing.Size($segW, 3)
        $seg.Location = New-Object System.Drawing.Point(($i * ($segW + 1)), 0)
        $seg.BackColor = [System.Drawing.Color]::FromArgb(255, 22, 26, 32)
        $barHost.Controls.Add($seg)
        $rects += $seg
    }
    $Toast.DismissRects = $rects

    $tickMs = [Math]::Max(30, [int]($Toast.Duration / $total))
    $interval = New-Object System.Windows.Forms.Timer
    $interval.Interval = $tickMs
    $state = @{ Toast = $Toast; Index = [ref]0; Accent = $Toast.Accent; Timer = $interval }
    $interval.Tag = $state
    $interval.Add_Tick({
        try {
            $local = $this.Tag
            $tt = $local.Toast
            if (-not $tt.Form -or $tt.Form.IsDisposed) { $this.Stop(); $this.Dispose(); return }
            $i = $local.Index.Value
            if ($i -ge $tt.DismissRects.Count) { $this.Stop(); $this.Dispose(); return }
            $seg = $tt.DismissRects[$i]
            if ($seg -and -not $seg.IsDisposed) {
                $seg.BackColor = $local.Accent
            }
            $local.Index.Value++
        } catch { try { $this.Stop(); $this.Dispose() } catch {} }
    })
    $Toast.DismissBarTimer = $interval
    $interval.Start()
}

function _Dismiss-ActiveToast {
    param([hashtable]$Toast, [switch]$Fast)
    if (-not $Toast -or $Toast.Dismissing) { return }
    $Toast.Dismissing = $true

    foreach ($key in @("LifetimeTimer","DismissBarTimer","SlideTimer","ReflowTimer")) {
        if ($Toast[$key]) {
            try { $Toast[$key].Stop(); $Toast[$key].Dispose() } catch {}
            $Toast[$key] = $null
        }
    }

    $steps = if ($Fast) { 6 } else { 12 }
    $step  = [ref]0
    $fade  = New-Object System.Windows.Forms.Timer
    $fade.Interval = 14
    $startY = $Toast.CurrentY
    $state = @{ Toast = $Toast; Step = $step; Steps = $steps; StartY = $startY }
    $fade.Tag = $state
    $fade.Add_Tick({
        try {
            $local = $this.Tag
            $tt = $local.Toast
            if (-not $tt.Form -or $tt.Form.IsDisposed) { $this.Stop(); $this.Dispose(); return }
            $local.Step.Value++
            $raw = [double]$local.Step.Value / $local.Steps
            if ($raw -ge 1) { $raw = 1 }
            $eased = 1 - [Math]::Pow(1 - $raw, 2)
            $tt.Form.Top = [int]($local.StartY - ($eased * 8))
            $tt.Form.Opacity = [Math]::Max(0, 0.97 - $eased * 0.97)
            if ($raw -ge 1) {
                $this.Stop(); $this.Dispose()
                try { $tt.Form.Hide() } catch {}
                try { $tt.Form.Close() } catch {}
                try { $tt.Form.Dispose() } catch {}
                # Remove from active list and drain queue
                if ($script:ActiveToasts.Contains($tt)) {
                    $null = $script:ActiveToasts.Remove($tt)
                }
                _Reflow-ToastStack
                _Drain-ToastQueue
            }
        } catch { try { $this.Stop(); $this.Dispose() } catch {} }
    })
    $Toast.FadeTimer = $fade
    $fade.Start()
}

function _Drain-ToastQueue {
    while ($script:ToastQueue.Count -gt 0 -and $script:ActiveToasts.Count -lt $script:ToastMaxVisible) {
        $q = $script:ToastQueue.Dequeue()
        $typeMeta = _Get-ToastTypeMeta -Type $q.Type
        $meta = _Format-ToastMeta -Meta $q.MetaText
        $key = "$($q.Type)|$($q.Title)|$($q.Message)"
        _Spawn-Toast -Title $q.Title -Message $q.Message -Type $q.Type `
            -TypeMeta $typeMeta -MetaText $meta -Duration $q.Duration -Key $key
    }
}

# ============================================================================
# PUBLIC: Close-ThemedToast (clears all)
# ============================================================================

function Close-ThemedToast {
    <#
    .SYNOPSIS
    Dismisses every active toast and empties the pending queue.
    Safe to call from shutdown paths.
    #>
    try { $script:ToastQueue.Clear() } catch {}
    $snapshot = @()
    foreach ($t in $script:ActiveToasts) { $snapshot += ,$t }
    foreach ($t in $snapshot) {
        try { _Dismiss-ActiveToast -Toast $t -Fast } catch {}
    }
}

# ============================================================================
# PROGRESS OVERLAY (palette re-skinned to match HUD; structure preserved)
# ============================================================================

$script:ProgressForm = $null
$script:ProgressLabel = $null
$script:ProgressBar = $null
$script:ProgressTimer = $null
$script:ProgressAngle = 0
$script:ProgressShimmerOffset = 0
$script:ProgressElapsedTimer = $null
$script:ProgressStartTime = $null

function Show-ProgressOverlay {
    <#
    .SYNOPSIS
    Shows a HUD-styled progress panel during profile application.
    .PARAMETER Title   Headline (e.g. "Applying Rivals 2: Online")
    .PARAMETER StepText Current step text
    #>
    param(
        [string]$Title = "APPLYING PROFILE",
        [string]$StepText = "Initializing..."
    )
    Close-ProgressOverlay
    _Ensure-ToastFonts

    $accentR = 0;    $accentG = 212;   $accentB = 255   # HUD cyan to match toasts

    $form = New-Object System.Windows.Forms.Form
    $form.Text = ""
    $form.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::None
    $form.BackColor = [System.Drawing.Color]::FromArgb(255, 11, 13, 16)
    $form.Size = New-Object System.Drawing.Size(400, 150)
    $form.StartPosition = [System.Windows.Forms.FormStartPosition]::Manual
    $form.TopMost = $true
    $form.ShowInTaskbar = $false
    $form.Opacity = 0

    $screen = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
    $form.Location = New-Object System.Drawing.Point(
        ($screen.Right - $form.Width - 16),
        ($screen.Bottom - $form.Height - 16)
    )

    $form.Add_Paint({
        param($s, $e)
        $g = $e.Graphics
        $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias

        # Background + hatch
        $panelBrush = New-Object System.Drawing.Drawing2D.LinearGradientBrush(
            (New-Object System.Drawing.Rectangle(0, 0, $s.Width, $s.Height)),
            [System.Drawing.Color]::FromArgb(255, 11, 13, 16),
            [System.Drawing.Color]::FromArgb(255, 15, 20, 26),
            [System.Drawing.Drawing2D.LinearGradientMode]::Vertical
        )
        $g.FillRectangle($panelBrush, 0, 0, $s.Width, $s.Height)
        $panelBrush.Dispose()
        $hatchPen = New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb(6,255,255,255),1)
        for ($x = -$s.Height; $x -lt $s.Width; $x += 7) {
            $g.DrawLine($hatchPen, $x, 0, ($x + $s.Height), $s.Height)
        }
        $hatchPen.Dispose()

        # Accent border + top stripe with tick breaks
        $borderPen = New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb(70,0,212,255), 1)
        $g.DrawRectangle($borderPen, 0, 0, ($s.Width - 1), ($s.Height - 1))
        $borderPen.Dispose()
        $topBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(220,0,212,255))
        $g.FillRectangle($topBrush, 0, 0, $s.Width, 2)
        $topBrush.Dispose()
        $tickBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(255,11,13,16))
        for ($tx = 44; $tx -lt $s.Width; $tx += 28) { $g.FillRectangle($tickBrush, $tx, 0, 1, 2) }
        $tickBrush.Dispose()

        # Left rail
        $railBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(220,0,212,255))
        $g.FillRectangle($railBrush, 0, 2, 3, ($s.Height - 4))
        $railBrush.Dispose()

        # Animated orbit spinner
        $spinAngle = $script:ProgressAngle * [Math]::PI / 180.0
        $cx = 28; $cy = 26; $rOrbit = 8
        for ($i = 3; $i -ge 0; $i--) {
            $a = ($script:ProgressAngle - $i * 26) * [Math]::PI / 180.0
            $ox = $cx + [Math]::Cos($a) * $rOrbit
            $oy = $cy + [Math]::Sin($a) * $rOrbit
            $alpha = [Math]::Max(30, 220 - $i * 55)
            $size  = [Math]::Max(3, 6 - $i)
            $brush = New-Object System.Drawing.SolidBrush(
                [System.Drawing.Color]::FromArgb($alpha, 0, 212, 255)
            )
            $g.FillEllipse($brush, ($ox - $size/2), ($oy - $size/2), $size, $size)
            $brush.Dispose()
        }
    })

    # Title label (Bahnschrift SemiBold Condensed, uppercase, cyan-tinted)
    $titleLabel = New-Object System.Windows.Forms.Label
    $titleLabel.Text = $Title.ToUpper()
    $titleLabel.ForeColor = [System.Drawing.Color]::FromArgb(255, 232, 236, 243)
    $titleLabel.Font = $script:ToastFont_Title
    $titleLabel.Location = New-Object System.Drawing.Point(50, 10)
    $titleLabel.Size = New-Object System.Drawing.Size(340, 22)
    $titleLabel.BackColor = [System.Drawing.Color]::Transparent
    $form.Controls.Add($titleLabel)

    # Step label (Segoe UI, dim)
    $stepLabel = New-Object System.Windows.Forms.Label
    $stepLabel.Text = $StepText
    $stepLabel.ForeColor = [System.Drawing.Color]::FromArgb(255, 166, 171, 182)
    $stepLabel.Font = $script:ToastFont_Body
    $stepLabel.Location = New-Object System.Drawing.Point(50, 38)
    $stepLabel.Size = New-Object System.Drawing.Size(340, 20)
    $stepLabel.BackColor = [System.Drawing.Color]::Transparent
    $form.Controls.Add($stepLabel)

    # Progress bar track + fill (indeterminate oscillator)
    $progressTrack = New-Object System.Windows.Forms.Panel
    $progressTrack.Location = New-Object System.Drawing.Point(16, 78)
    $progressTrack.Size = New-Object System.Drawing.Size(368, 6)
    $progressTrack.BackColor = [System.Drawing.Color]::FromArgb(255, 22, 26, 32)

    $progressFill = New-Object System.Windows.Forms.Panel
    $progressFill.Location = New-Object System.Drawing.Point(0, 0)
    $progressFill.Size = New-Object System.Drawing.Size(0, 6)
    $progressFill.BackColor = [System.Drawing.Color]::Transparent
    $progressFill.Add_Paint({
        param($s, $e)
        if ($s.Width -le 1) { return }
        $g = $e.Graphics
        try {
            $fill = New-Object System.Drawing.Drawing2D.LinearGradientBrush(
                (New-Object System.Drawing.Rectangle(0, 0, [Math]::Max(2, $s.Width), $s.Height)),
                [System.Drawing.Color]::FromArgb(255, 0, 150, 200),
                [System.Drawing.Color]::FromArgb(255, 80, 230, 255),
                [System.Drawing.Drawing2D.LinearGradientMode]::Horizontal
            )
            $g.FillRectangle($fill, 0, 0, $s.Width, $s.Height)
            $fill.Dispose()
        } catch {
            $solid = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(255,0,212,255))
            $g.FillRectangle($solid, 0, 0, $s.Width, $s.Height)
            $solid.Dispose()
        }
        $shX = $script:ProgressShimmerOffset
        if ($shX -lt $s.Width) {
            $sh = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(60,255,255,255))
            $g.FillRectangle($sh, $shX, 0, [Math]::Min(60, $s.Width - $shX), $s.Height)
            $sh.Dispose()
        }
    })
    $progressTrack.Controls.Add($progressFill)
    $form.Controls.Add($progressTrack)

    # Animation timer
    $timer = New-Object System.Windows.Forms.Timer
    $script:ProgressTimer = $timer
    $timer.Interval = 45
    $script:ProgressAngle = 0
    $script:ProgressShimmerOffset = -60
    $timer.Add_Tick({
        try {
            $script:ProgressAngle = ($script:ProgressAngle + 9) % 360
            if ($script:ProgressForm -and $script:ProgressBar -and -not $script:ProgressForm.IsDisposed) {
                $barWidth = 110
                $maxX = 368
                $cycle = ($script:ProgressAngle * 2) % ($maxX * 2)
                $x = if ($cycle -lt $maxX) { $cycle } else { $maxX * 2 - $cycle }
                $x = [int]$x
                if (($x + $barWidth) -gt $maxX) { $barWidth = $maxX - $x }
                $script:ProgressBar.Location = New-Object System.Drawing.Point($x, 0)
                $script:ProgressBar.Size = New-Object System.Drawing.Size([Math]::Max(1, $barWidth), 6)
                $script:ProgressShimmerOffset += 4
                if ($script:ProgressShimmerOffset -gt $barWidth + 60) { $script:ProgressShimmerOffset = -60 }
                $script:ProgressBar.Invalidate()
                $script:ProgressForm.Invalidate()
            }
        } catch { try { $timer.Stop() } catch {} }
    })
    $timer.Start()

    # Elapsed time (monospace)
    $elapsedLabel = New-Object System.Windows.Forms.Label
    $elapsedLabel.Text = "0.0s"
    $elapsedLabel.ForeColor = [System.Drawing.Color]::FromArgb(255, 96, 102, 111)
    $elapsedLabel.Font = $script:ToastFont_Meta
    $elapsedLabel.Location = New-Object System.Drawing.Point(16, 108)
    $elapsedLabel.Size = New-Object System.Drawing.Size(80, 16)
    $elapsedLabel.BackColor = [System.Drawing.Color]::Transparent
    $form.Controls.Add($elapsedLabel)

    $cancelLabel = New-Object System.Windows.Forms.Label
    $cancelLabel.Text = "CANCEL"
    $cancelLabel.ForeColor = [System.Drawing.Color]::FromArgb(255, 96, 102, 111)
    $cancelLabel.Font = $script:ToastFont_Badge
    $cancelLabel.Location = New-Object System.Drawing.Point(330, 106)
    $cancelLabel.Size = New-Object System.Drawing.Size(60, 20)
    $cancelLabel.BackColor = [System.Drawing.Color]::Transparent
    $cancelLabel.Cursor = [System.Windows.Forms.Cursors]::Hand
    $cancelLabel.TextAlign = [System.Drawing.ContentAlignment]::MiddleRight
    $cancelLabel.Add_MouseEnter({ $this.ForeColor = [System.Drawing.Color]::FromArgb(255,255,77,94) })
    $cancelLabel.Add_MouseLeave({ $this.ForeColor = [System.Drawing.Color]::FromArgb(255,96,102,111) })
    $form.Controls.Add($cancelLabel)

    $script:ProgressStartTime = Get-Date
    $elapsedTimer = New-Object System.Windows.Forms.Timer
    $elapsedTimer.Interval = 100
    $captured = $elapsedLabel
    $elapsedTimer.Add_Tick({
        try {
            if ($captured -and -not $captured.IsDisposed) {
                $s = ((Get-Date) - $script:ProgressStartTime).TotalSeconds
                $captured.Text = ("{0:N1}s" -f $s)
            }
        } catch { try { $elapsedTimer.Stop() } catch {} }
    })
    $elapsedTimer.Start()
    $script:ProgressElapsedTimer = $elapsedTimer

    $script:ProgressForm  = $form
    $script:ProgressLabel = $stepLabel
    $script:ProgressBar   = $progressFill

    $form.Show()

    try {
        if ("DwmHelper" -as [type]) {
            Apply-DwmWindowEffects -Form $form -CornerStyle 3 -BorderColorRGB @($accentR, $accentG, $accentB)
        }
    } catch {}

    # Fade in
    $fadeIn = New-Object System.Windows.Forms.Timer
    $fadeIn.Interval = 14
    $fadeIn.Add_Tick({
        try {
            if ($script:ProgressForm -and -not $script:ProgressForm.IsDisposed) {
                $op = $script:ProgressForm.Opacity + 0.12
                if ($op -ge 0.97) { $script:ProgressForm.Opacity = 0.97; $this.Stop(); $this.Dispose() }
                else              { $script:ProgressForm.Opacity = $op }
            } else { $this.Stop(); $this.Dispose() }
        } catch { try { $this.Stop(); $this.Dispose() } catch {} }
    })
    $fadeIn.Start()
}

function Update-ProgressOverlay {
    param([string]$StepText)
    if ($script:ProgressForm -and $script:ProgressLabel -and -not $script:ProgressForm.IsDisposed) {
        $script:ProgressLabel.Text = $StepText
        $script:ProgressForm.Refresh()
    }
}

function Close-ProgressOverlay {
    if ($script:ProgressElapsedTimer) {
        try { $script:ProgressElapsedTimer.Stop(); $script:ProgressElapsedTimer.Dispose() } catch {}
        $script:ProgressElapsedTimer = $null
    }
    if ($script:ProgressTimer) {
        try { $script:ProgressTimer.Stop(); $script:ProgressTimer.Dispose() } catch {}
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
    $script:ProgressBar   = $null
}

# ============================================================================
# Legacy compat
# ============================================================================

function Show-ABSONotification {
    param(
        [string]$Title,
        [string]$Message,
        [ValidateSet("Info","Warning","Error","Success")]
        [string]$Type = "Info",
        [System.Windows.Forms.NotifyIcon]$NotifyIcon,
        [int]$Duration = 4500,
        [string]$MetaText = ""
    )
    if ($NotifyIcon) {
        $maxLen = [Math]::Min(63, "$Title - $Message".Length)
        $NotifyIcon.Text = "$Title - $Message".Substring(0, $maxLen)
    }
    Show-ThemedToast -Title $Title -Message $Message -Type $Type -Duration $Duration -MetaText $MetaText
}

# ============================================================================
# Status bar (unchanged behavior, re-skinned palette)
# ============================================================================

function New-StatusBarItem {
    param(
        [string]$LastAction = "Ready",
        [string]$LastActionTime = "",
        [string]$CurrentGame = "",
        [string]$BackupTime = ""
    )
    $parts = @()
    if ($LastAction)  { $parts += $LastAction }
    if ($CurrentGame) { $parts += "Game: $CurrentGame" }
    if ($BackupTime)  { $parts += "Backup: $BackupTime" }
    $text = $parts -join "  |  "
    $item = New-Object System.Windows.Forms.ToolStripMenuItem
    $item.Text = "  $text"
    $item.Enabled = $false
    $item.BackColor = [System.Drawing.Color]::FromArgb(255, 15, 20, 26)
    $item.ForeColor = [System.Drawing.Color]::FromArgb(255, 96, 102, 111)
    $item.Font = New-Object System.Drawing.Font("Cascadia Mono", 7.5)
    return $item
}
