# ABSO-Notifications.ps1 - v5.0 "Phosphor" retro-gaming HUD notifications
#
# Tron / retro-arcade HUD aesthetic - geometric condensed type, electric
# phosphor cyan accent, decorative L-brackets, CRT scanlines, tick-marked
# accent rails. Designed to read as 'gaming peripheral OSD' or 'fighting
# game training-mode overlay', not generic Windows toast.
#
#   * Bahnschrift SemiBold Condensed headlines (geometric Win11 native HUD type)
#   * Cascadia Code body + footer (developer/console mono with slashed zero)
#   * Single phosphor accent per state (cyan #00F5D4 default; status hues for
#     success/warn/error)
#   * Deep ink base + vertical gradient + faint CRT scanlines + grain
#   * 6px left accent rail with tick perforations every 22px
#   * 8px L-shaped corner brackets (TL + BR) in accent
#   * Refresh-rate Hz badge in the corner - reads the user's actual monitor
#   * Single hairline rule under the headline
#   * Recedinghairline dismiss bar (right -> left over duration)
#   * Click anywhere to dismiss; no chrome X
#   * Animation timer interval adapts to monitor refresh rate (8ms floor)
#   * Per-toast isolated state (no shared-slot stomp)
#
# Public API preserved verbatim: Show-ThemedToast, Close-ThemedToast,
# Show-ProgressOverlay, Update-ProgressOverlay, Close-ProgressOverlay,
# Show-ABSONotification, New-StatusBarItem.

# ============================================================================
# STATE
# ============================================================================

$script:ActiveToasts       = [System.Collections.Generic.List[object]]::new()
$script:ToastQueue         = [System.Collections.Generic.Queue[object]]::new()
$script:ToastQueueMaxSize  = 16    # protect against runaway producers
$script:ToastDedupMap      = @{}
$script:ToastDedupMaxSize  = 200   # bounded eviction so the map doesn't grow forever
$script:ToastMaxVisible    = 3
$script:ToastSlotGap       = 8
$script:ToastRightMargin   = 18
$script:ToastBottomMargin  = 18
$script:ToastWidth         = 480   # production messages are 300-500ch; 420 was too narrow
$script:ToastDedupWindowMs = 2000
$script:ToastChapterSeq    = 0     # monotonic "chapter" counter for the corner mark

function _Evict-DedupMap {
    <#
    .SYNOPSIS
    Drop dedup entries older than the dedup window and, if still over the
    size cap, drop the oldest entries until back under the cap. Called from
    Show-ThemedToast before inserting a new key so the map stays bounded.
    #>
    if (-not $script:ToastDedupMap -or $script:ToastDedupMap.Count -le 16) { return }
    $nowMs = [DateTimeOffset]::Now.ToUnixTimeMilliseconds()
    $cutoff = $nowMs - ($script:ToastDedupWindowMs * 4)
    $expired = @($script:ToastDedupMap.GetEnumerator() | Where-Object { $_.Value -lt $cutoff } | ForEach-Object { $_.Key })
    foreach ($k in $expired) { $script:ToastDedupMap.Remove($k) }
    if ($script:ToastDedupMap.Count -gt $script:ToastDedupMaxSize) {
        $ordered = @($script:ToastDedupMap.GetEnumerator() | Sort-Object Value | ForEach-Object { $_.Key })
        $surplus = $script:ToastDedupMap.Count - $script:ToastDedupMaxSize
        for ($i = 0; $i -lt $surplus; $i++) { $script:ToastDedupMap.Remove($ordered[$i]) }
    }
}

# ============================================================================
# PHOSPHOR PALETTE
# ============================================================================
#
# Single source of truth for the toast/progress/status surfaces. Phosphor
# cyan is the brand color - it appears on the left rail, corner brackets,
# rule, and Hz badge. Status hues (moss/ochre/coral) only override the
# accent for non-info toasts.
$script:Penumbra = if (Get-Command Get-TrayThemePalette -ErrorAction SilentlyContinue) {
    Get-TrayThemePalette
}
else {
    @{
        Ink100   = [System.Drawing.Color]::FromArgb(255, 14, 18, 26)    # base
        Ink200   = [System.Drawing.Color]::FromArgb(255, 19, 24, 36)    # gradient bottom
        Ink300   = [System.Drawing.Color]::FromArgb(255, 27, 34, 48)    # elevated / label bg
        Ink150   = [System.Drawing.Color]::FromArgb(255, 17, 21, 31)    # label background midpoint
        Paper    = [System.Drawing.Color]::FromArgb(255, 232, 238, 246) # primary text
        Mist     = [System.Drawing.Color]::FromArgb(255, 150, 162, 183) # secondary text
        Fog      = [System.Drawing.Color]::FromArgb(255, 92, 104, 128)  # tertiary / mono
        Rule     = [System.Drawing.Color]::FromArgb(70, 0, 245, 212)    # phosphor hairline
        Lagoon   = [System.Drawing.Color]::FromArgb(255, 0, 245, 212)   # phosphor cyan
        Moss     = [System.Drawing.Color]::FromArgb(255, 123, 227, 158) # success
        Ochre    = [System.Drawing.Color]::FromArgb(255, 229, 165, 71)  # warning
        Coral    = [System.Drawing.Color]::FromArgb(255, 255, 107, 107) # error
    }
}

# Font cache (resolved once with full fallback chain).
# Phosphor type system: Bahnschrift Condensed for HUD headlines (geometric,
# tracks well at small sizes, ships native on Win10+), Cascadia Code for
# body/mono (developer font, slashed zero, has ligatures).
$script:Font_Eyebrow = $null   # tracked condensed caps   - "STATUS / INFO"
$script:Font_Title   = $null   # Bahnschrift headline     - the toast headline
$script:Font_Body    = $null   # Cascadia Code body       - the message
$script:Font_Mono    = $null   # Cascadia Code mono       - footer
$script:Font_Tag     = $null   # Cascadia Code small      - chapter marker + Hz badge

function _Resolve-Font {
    param(
        [string[]]$Families,
        [float]$Size,
        [System.Drawing.FontStyle]$Style = [System.Drawing.FontStyle]::Regular
    )
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

function _Ensure-Fonts {
    if ($null -ne $script:Font_Title) { return }
    $script:Font_Eyebrow = _Resolve-Font `
        -Families @("Bahnschrift SemiBold Condensed", "Bahnschrift Condensed", "Bahnschrift", "Segoe UI Semibold") `
        -Size 8.0 -Style ([System.Drawing.FontStyle]::Bold)
    $script:Font_Title   = _Resolve-Font `
        -Families @("Bahnschrift SemiBold Condensed", "Bahnschrift Condensed", "Bahnschrift", "Segoe UI Semibold") `
        -Size 15.5 -Style ([System.Drawing.FontStyle]::Bold)
    $script:Font_Body    = _Resolve-Font `
        -Families @("Cascadia Code", "Cascadia Mono", "Consolas") `
        -Size 9.0 -Style ([System.Drawing.FontStyle]::Regular)
    $script:Font_Mono    = _Resolve-Font `
        -Families @("Cascadia Code", "Cascadia Mono", "Consolas") `
        -Size 8.5 -Style ([System.Drawing.FontStyle]::Regular)
    $script:Font_Tag     = _Resolve-Font `
        -Families @("Cascadia Code", "Cascadia Mono", "Consolas") `
        -Size 8.0 -Style ([System.Drawing.FontStyle]::Bold)
}

# ============================================================================
# REFRESH-RATE-ADAPTIVE FRAME INTERVAL
# ============================================================================
#
# Reads the primary monitor's refresh rate once at module load and exposes
# $script:FrameInterval (ms) for every animation timer. WinForms Timer can't
# reliably fire faster than ~8ms (125fps), so that's the floor regardless of
# refresh rate. Above 125Hz the panel will still feel buttery thanks to the
# combination of shorter steps and ease curves. The Hz value is also shown
# as a small badge so the user can see we're respecting their hardware.
$script:RefreshRate = 60
$script:FrameInterval = 16

function _Detect-RefreshRate {
    try {
        $hz = (Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue |
               Where-Object { $_.CurrentRefreshRate -gt 0 } |
               Sort-Object CurrentRefreshRate -Descending |
               Select-Object -First 1).CurrentRefreshRate
        if ($hz -ge 30 -and $hz -le 600) { return [int]$hz }
    } catch {}
    return 60
}
$script:RefreshRate   = _Detect-RefreshRate
$script:FrameInterval = [Math]::Max(8, [int]([Math]::Floor(1000.0 / $script:RefreshRate)))
$script:HzBadgeText   = "{0}Hz" -f $script:RefreshRate

# ============================================================================
# Z-ORDER HARDENING (Win32 SetWindowPos)
# ============================================================================
#
# WinForms `Form.TopMost = $true` competes with other TopMost apps and Discord
# in particular periodically re-asserts itself, painting over our toast and
# progress overlay. SetWindowPos with HWND_TOPMOST + NOACTIVATE flags is the
# stronger assertion; a periodic 600ms re-call keeps us above other contenders.
if (-not ("AbsoZOrder" -as [type])) {
    Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class AbsoZOrder {
    [DllImport("user32.dll")]
    public static extern bool SetWindowPos(IntPtr hWnd, IntPtr hWndInsertAfter,
        int X, int Y, int cx, int cy, uint uFlags);
    public static readonly IntPtr HWND_TOPMOST = new IntPtr(-1);
    public const uint SWP_NOMOVE       = 0x0002;
    public const uint SWP_NOSIZE       = 0x0001;
    public const uint SWP_NOACTIVATE   = 0x0010;
    public const uint SWP_SHOWWINDOW   = 0x0040;
    public static void ForceTopmost(IntPtr hWnd) {
        SetWindowPos(hWnd, HWND_TOPMOST, 0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE);
    }
}
"@ -ErrorAction SilentlyContinue
}

# ============================================================================
# STATE METADATA (accent, eyebrow tag, priority, audio sentinel)
# ============================================================================

function _Get-ToastTypeMeta {
    param([string]$Type)
    switch ($Type) {
        "Success" {
            return @{
                Accent   = $script:Penumbra.Moss
                Eyebrow  = "STATUS / SUCCESS"
                Priority = 2
            }
        }
        "Warning" {
            return @{
                Accent   = $script:Penumbra.Ochre
                Eyebrow  = "STATUS / NOTICE"
                Priority = 3
            }
        }
        "Error" {
            return @{
                Accent   = $script:Penumbra.Coral
                Eyebrow  = "STATUS / FAILURE"
                Priority = 4
            }
        }
        default {
            return @{
                Accent   = $script:Penumbra.Lagoon
                Eyebrow  = "STATUS / INFO"
                Priority = 1
            }
        }
    }
}

# ============================================================================
# TITLE + METADATA DERIVATION
# ============================================================================

function _Smart-Truncate {
    <#
    .SYNOPSIS
    Truncate at the LAST word boundary before $MaxLen, appending an ellipsis.
    Beats brute-character cuts that leave words split or parens unclosed.
    #>
    param([string]$Text, [int]$MaxLen)
    if (-not $Text) { return "" }
    $t = $Text.Trim()
    if ($t.Length -le $MaxLen) { return $t }
    $cut = $t.Substring(0, $MaxLen)
    $space = $cut.LastIndexOf(' ')
    if ($space -gt ($MaxLen / 2)) { $cut = $cut.Substring(0, $space) }
    return $cut.TrimEnd(' ', ',', ';', ':', '|', '-', '/') + [char]0x2026
}

function _Derive-ToastTitle {
    param([string]$RawTitle, [string]$Message, [string]$Type)
    # Production titles look like "Overwatch 2 - GSYNC HDR (Overlay-Free HDR Borderless | Reflex | G-SYNC ON)".
    # Cutting at 56 chars leaves unclosed parens. Cut at the first " (" or " |"
    # boundary so we keep the profile name intact and drop the mode list.
    $trim = "$RawTitle".Trim()
    $genericTitles = @("computa", "Computa", "A.B.S.O.", "A.B.S.O", "ABSO", "")
    $title = $null
    if ($genericTitles -notcontains $trim -and $trim -inotlike "computa*" -and $trim -inotlike "A.B.S.O*") {
        $title = $trim
    }
    elseif ($trim -ilike "computa*" -or $trim -ilike "A.B.S.O*") {
        $suffix = ($trim -replace '^(computa|A\.B\.S\.O\.?)\s*', '').Trim()
        if ($suffix) { $title = $suffix }
    }
    if (-not $title) {
        $msg = "$Message".Trim()
        if (-not $msg) {
            switch ($Type) {
                "Success" { return "Tray action complete" }
                "Warning" { return "Tray warning" }
                "Error"   { return "Tray error" }
                default   { return "Tray status" }
            }
        }
        $title = ($msg -split '[.!?:|]', 2)[0].Trim()
    }
    # Strip a parenthesized mode list ("(Strict HDR | Reflex | G-SYNC ON)") - too long for a headline.
    $title = ($title -replace '\s*\([^()]*\)\s*$', '').Trim()
    # If the headline still has " | " separators AND would overflow the 62-char headline
    # budget, keep only the first segment. We do NOT pre-chop short pipe-separated names
    # (e.g. "Game | Variant") because that throws away legitimate name parts.
    if ($title.Length -gt 62 -and $title -match '\s\|\s') {
        $title = ($title -split '\s\|\s', 2)[0].Trim()
    }
    return (_Smart-Truncate -Text $title -MaxLen 62)
}

function _Derive-ToastBody {
    <#
    .SYNOPSIS
    Trim the production body to a single legible block: take the first
    sentence, cap at ~220 chars, end at a word boundary. Long pipe-separated
    detail lists are clipped here because the toast can't show them all.
    #>
    param([string]$Message)
    if (-not $Message) { return "" }
    $m = "$Message".Trim()
    # If the message has a clear first sentence (ending in . ! or ?), prefer that
    # WHEN the sentence is reasonably substantive (>= 30 chars) - otherwise the
    # message body is probably just one fact that happens to end mid-sentence.
    $firstStop = [Regex]::Match($m, '^[^.!?]{30,}[.!?](\s|$)')
    if ($firstStop.Success -and $firstStop.Length -lt 240) {
        $m = $firstStop.Value.Trim()
    }
    return (_Smart-Truncate -Text $m -MaxLen 220)
}

function _Format-ToastFooter {
    param([string]$Meta)
    $time = (Get-Date).ToString("HH:mm:ss")
    $dot  = " " + [char]0x00B7 + " "
    if ($Meta) {
        return ("{0}{1}{2}" -f $time, $dot, $Meta)
    }
    return $time
}

function _Format-ChapterMark {
    param([int]$Seq)
    return ("No. {0:D2}" -f $Seq)
}

# ============================================================================
# SLOT LAYOUT
# ============================================================================

function _Compute-ToastTargetY {
    param([int]$IndexFromBottom, [int]$Height)
    $screen  = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
    $yBottom = $screen.Bottom - $script:ToastBottomMargin
    $accum   = 0
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
    for ($i = 0; $i -lt $script:ActiveToasts.Count; $i++) {
        $t = $script:ActiveToasts[$i]
        if (-not $t.Form -or $t.Form.IsDisposed) { continue }
        $targetY = _Compute-ToastTargetY -IndexFromBottom $i -Height $t.Height
        $t.TargetY = $targetY
        if ($t.ReflowTimer) {
            try { $t.ReflowTimer.Stop(); $t.ReflowTimer.Dispose() } catch {}
        }
        $timer = New-Object System.Windows.Forms.Timer
        $timer.Interval = $script:FrameInterval
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
                $step = [Math]::Sign($diff) * [Math]::Max(1, [Math]::Ceiling([Math]::Abs($diff) * 0.26))
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
# PANEL PAINT (Penumbra surface treatment)
# ============================================================================
#
# Scanline + grain overlays were removed because they raised the form's
# effective brightness above pure Ink-100 and the labels (which keep a
# solid Ink-100 BackColor to avoid transparency-cache races) then rendered
# as visibly darker rectangle cards. The helper that pre-generated grain
# pixel positions and its cache went with them.

function _Paint-ToastPanel {
    param(
        [System.Drawing.Graphics]$g,
        [int]$Width,
        [int]$Height,
        [hashtable]$Meta,
        [string]$ChapterText
    )
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::ClearTypeGridFit

    # 1) Solid base ink. Labels use the same Ink-100 BackColor so they blend
    #    invisibly into the base. Scanlines + film grain were tried as an
    #    aesthetic overlay but they brightened the form's effective color
    #    above pure Ink-100, which made the (still-pure-Ink-100) labels
    #    render as darker rectangle cards cut into the brighter surface.
    #    Removed for a flat-ink chassis - the L-brackets, rail, tick
    #    perforations, accent outline, chapter mark, and Hz badge carry
    #    enough HUD character without that compositing conflict.
    $baseBrush = New-Object System.Drawing.SolidBrush($script:Penumbra.Ink100)
    $g.FillRectangle($baseBrush, 0, 0, $Width, $Height)
    $baseBrush.Dispose()

    # 4) Outline (full panel hairline in accent at low alpha)
    $outlinePen = New-Object System.Drawing.Pen(
        [System.Drawing.Color]::FromArgb(80, $Meta.Accent.R, $Meta.Accent.G, $Meta.Accent.B), 1
    )
    $g.DrawRectangle($outlinePen, 0, 0, ($Width - 1), ($Height - 1))
    $outlinePen.Dispose()

    # 5) Left accent rail - 6px solid + 1px feather + tick perforations
    $strokeBrush = New-Object System.Drawing.SolidBrush($Meta.Accent)
    $g.FillRectangle($strokeBrush, 0, 0, 6, $Height)
    $strokeBrush.Dispose()
    $featherBrush = New-Object System.Drawing.SolidBrush(
        [System.Drawing.Color]::FromArgb(80, $Meta.Accent.R, $Meta.Accent.G, $Meta.Accent.B)
    )
    $g.FillRectangle($featherBrush, 6, 0, 1, $Height)
    $featherBrush.Dispose()
    # Tick perforations every 22px - dark notches across the rail
    $tickBrush = New-Object System.Drawing.SolidBrush($script:Penumbra.Ink100)
    for ($ty = 14; $ty -lt ($Height - 6); $ty += 22) {
        $g.FillRectangle($tickBrush, 0, $ty, 6, 1)
    }
    $tickBrush.Dispose()

    # 6) L-shaped corner brackets (top-right, bottom-left, bottom-right) in accent
    $bracketLen = 10
    $bracketPen = New-Object System.Drawing.Pen($Meta.Accent, 1.6)
    # Top-right: |_  shape
    $g.DrawLine($bracketPen, ($Width - $bracketLen - 2), 2, ($Width - 2), 2)
    $g.DrawLine($bracketPen, ($Width - 2), 2, ($Width - 2), ($bracketLen + 2))
    # Bottom-right: ^| shape
    $g.DrawLine($bracketPen, ($Width - 2), ($Height - $bracketLen - 2), ($Width - 2), ($Height - 2))
    $g.DrawLine($bracketPen, ($Width - $bracketLen - 2), ($Height - 2), ($Width - 2), ($Height - 2))
    # Bottom-left (just the horizontal arm; the vertical is the accent rail)
    $g.DrawLine($bracketPen, 6, ($Height - 2), ($bracketLen + 6), ($Height - 2))
    $bracketPen.Dispose()

    # 7) Chapter mark in top-right corner ("[ NO.04 ]" mono style)
    $chapterDisplay = "[ {0} ]" -f $ChapterText
    $chapterBrush = New-Object System.Drawing.SolidBrush(
        [System.Drawing.Color]::FromArgb(180, $Meta.Accent.R, $Meta.Accent.G, $Meta.Accent.B)
    )
    $chapterSize = $g.MeasureString($chapterDisplay, $script:Font_Tag)
    $g.DrawString($chapterDisplay, $script:Font_Tag, $chapterBrush,
        ($Width - $chapterSize.Width - 18), 10)
    $chapterBrush.Dispose()

    # 8) Refresh-rate Hz badge in the bottom-right corner (subtle gamer flex)
    $hzBrush = New-Object System.Drawing.SolidBrush($script:Penumbra.Fog)
    $hzSize = $g.MeasureString($script:HzBadgeText, $script:Font_Tag)
    $g.DrawString($script:HzBadgeText, $script:Font_Tag, $hzBrush,
        ($Width - $hzSize.Width - 18), ($Height - $hzSize.Height - 10))
    $hzBrush.Dispose()
}

function New-ProfileMarkMedallionBitmap {
    <#
    .SYNOPSIS
    Wraps a game/profile mark in the same circular glow/ring treatment used by
    the tray hero surfaces, sized for toast and progress panels.
    #>
    param(
        [string]$ProfileGameGroup,
        [string]$ProfileCategory = "Other",
        [System.Drawing.Color]$Color = [System.Drawing.Color]::White,
        [switch]$ActiveBadge,
        [string]$ModeBadge = "",
        [switch]$FavoriteBadge
    )

    if ([string]::IsNullOrWhiteSpace($ProfileGameGroup) -or -not (Get-Command New-GameBitmap -ErrorAction SilentlyContinue)) {
        return $null
    }

    $mark = $null
    $bmp = $null
    $g = $null
    $glowBrush = $null
    $backBrush = $null
    $ringPen = $null
    $tickPen = $null
    $shineBrush = $null
    try {
        if ($ActiveBadge -and (Get-Command New-ActiveGameBitmap -ErrorAction SilentlyContinue)) {
            $mark = New-ActiveGameBitmap `
                -GameGroup $ProfileGameGroup `
                -Color $Color `
                -Category $ProfileCategory `
                -ModeBadge $ModeBadge `
                -FavoriteBadge ([bool]$FavoriteBadge)
        }
        elseif ($FavoriteBadge -and (Get-Command New-FavoriteGameBitmap -ErrorAction SilentlyContinue)) {
            $mark = New-FavoriteGameBitmap `
                -GameGroup $ProfileGameGroup `
                -Color $Color `
                -Category $ProfileCategory `
                -ModeBadge $ModeBadge
        }
        elseif (-not [string]::IsNullOrWhiteSpace($ModeBadge) -and (Get-Command New-GameSyncBadgeBitmap -ErrorAction SilentlyContinue)) {
            $mark = New-GameSyncBadgeBitmap `
                -GameGroup $ProfileGameGroup `
                -Color $Color `
                -Category $ProfileCategory `
                -SyncMode "agnostic" `
                -ModeBadge $ModeBadge
        }
        else {
            $mark = New-GameBitmap -GameGroup $ProfileGameGroup -Color $Color -Category $ProfileCategory
        }
        if (-not $mark) { return $null }

        $bmp = New-Object System.Drawing.Bitmap(36, 36)
        $g = [System.Drawing.Graphics]::FromImage($bmp)
        $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
        $g.Clear([System.Drawing.Color]::Transparent)

        $glowBrush = New-Object System.Drawing.SolidBrush -ArgumentList (
            [System.Drawing.Color]::FromArgb(54, $Color.R, $Color.G, $Color.B)
        )
        $g.FillEllipse($glowBrush, 1, 1, 34, 34)

        $backRect = New-Object System.Drawing.Rectangle(5, 5, 26, 26)
        $backBrush = New-Object System.Drawing.Drawing2D.LinearGradientBrush(
            $backRect,
            [System.Drawing.Color]::FromArgb(235, 19, 24, 36),
            [System.Drawing.Color]::FromArgb(245, 10, 14, 21),
            [System.Drawing.Drawing2D.LinearGradientMode]::ForwardDiagonal
        )
        $g.FillEllipse($backBrush, $backRect)

        $ringPen = New-Object System.Drawing.Pen -ArgumentList (
            [System.Drawing.Color]::FromArgb(180, $Color.R, $Color.G, $Color.B), 1.4
        )
        $g.DrawEllipse($ringPen, 5, 5, 26, 26)

        $tickPen = New-Object System.Drawing.Pen -ArgumentList (
            [System.Drawing.Color]::FromArgb(110, $Color.R, $Color.G, $Color.B), 1.1
        )
        $tickPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
        $tickPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
        $g.DrawArc($tickPen, 3, 3, 30, 30, 212, 42)
        $g.DrawArc($tickPen, 3, 3, 30, 30, 326, 34)

        $g.DrawImage($mark, (New-Object System.Drawing.Rectangle(9, 9, 18, 18)))

        $shineBrush = New-Object System.Drawing.SolidBrush -ArgumentList (
            [System.Drawing.Color]::FromArgb(80, 255, 255, 255)
        )
        $g.FillEllipse($shineBrush, 10, 7, 8, 4)

        return $bmp
    }
    catch {
        if ($bmp) {
            try { $bmp.Dispose() } catch {}
            $bmp = $null
        }
        return $null
    }
    finally {
        if ($shineBrush) { $shineBrush.Dispose() }
        if ($tickPen) { $tickPen.Dispose() }
        if ($ringPen) { $ringPen.Dispose() }
        if ($backBrush) { $backBrush.Dispose() }
        if ($glowBrush) { $glowBrush.Dispose() }
        if ($g) { $g.Dispose() }
        if ($mark) { $mark.Dispose() }
    }
}

function New-ActionMarkMedallionBitmap {
    <#
    .SYNOPSIS
    Wraps a tray action glyph in the same toast medallion treatment used by
    profile toasts, so action-only notices are not visually generic.
    #>
    param(
        [string]$ActionName,
        [System.Drawing.Color]$Color = [System.Drawing.Color]::White
    )

    if ([string]::IsNullOrWhiteSpace($ActionName) -or -not (Get-Command New-ActionBitmap -ErrorAction SilentlyContinue)) {
        return $null
    }

    $mark = $null
    $bmp = $null
    $g = $null
    $glowBrush = $null
    $backBrush = $null
    $ringPen = $null
    $tickPen = $null
    $shineBrush = $null
    try {
        $mark = New-ActionBitmap -Action $ActionName -Color $Color
        if (-not $mark) { return $null }

        $bmp = New-Object System.Drawing.Bitmap(36, 36)
        $g = [System.Drawing.Graphics]::FromImage($bmp)
        $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
        $g.Clear([System.Drawing.Color]::Transparent)

        $glowBrush = New-Object System.Drawing.SolidBrush -ArgumentList (
            [System.Drawing.Color]::FromArgb(48, $Color.R, $Color.G, $Color.B)
        )
        $g.FillEllipse($glowBrush, 1, 1, 34, 34)

        $backRect = New-Object System.Drawing.Rectangle(5, 5, 26, 26)
        $backBrush = New-Object System.Drawing.Drawing2D.LinearGradientBrush(
            $backRect,
            [System.Drawing.Color]::FromArgb(235, 19, 24, 36),
            [System.Drawing.Color]::FromArgb(245, 10, 14, 21),
            [System.Drawing.Drawing2D.LinearGradientMode]::ForwardDiagonal
        )
        $g.FillEllipse($backBrush, $backRect)

        $ringPen = New-Object System.Drawing.Pen -ArgumentList (
            [System.Drawing.Color]::FromArgb(170, $Color.R, $Color.G, $Color.B), 1.35
        )
        $g.DrawEllipse($ringPen, 5, 5, 26, 26)

        $tickPen = New-Object System.Drawing.Pen -ArgumentList (
            [System.Drawing.Color]::FromArgb(95, $Color.R, $Color.G, $Color.B), 1.05
        )
        $tickPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
        $tickPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
        $g.DrawArc($tickPen, 3, 3, 30, 30, 218, 38)
        $g.DrawArc($tickPen, 3, 3, 30, 30, 324, 30)

        $g.DrawImage($mark, (New-Object System.Drawing.Rectangle(10, 10, 16, 16)))

        $shineBrush = New-Object System.Drawing.SolidBrush -ArgumentList (
            [System.Drawing.Color]::FromArgb(72, 255, 255, 255)
        )
        $g.FillEllipse($shineBrush, 10, 7, 8, 4)

        return $bmp
    }
    catch {
        if ($bmp) {
            try { $bmp.Dispose() } catch {}
            $bmp = $null
        }
        return $null
    }
    finally {
        if ($shineBrush) { $shineBrush.Dispose() }
        if ($tickPen) { $tickPen.Dispose() }
        if ($ringPen) { $ringPen.Dispose() }
        if ($backBrush) { $backBrush.Dispose() }
        if ($glowBrush) { $glowBrush.Dispose() }
        if ($g) { $g.Dispose() }
        if ($mark) { $mark.Dispose() }
    }
}

# ============================================================================
# FORM CONSTRUCTION
# ============================================================================

function _Build-ToastForm {
    param(
        [string]$Title,
        [string]$Message,
        [string]$FooterText,
        [hashtable]$TypeMeta,
        [string]$ChapterText,
        [string]$ProfileGameGroup = "",
        [string]$ProfileCategory = "Other",
        [System.Drawing.Color]$ProfileColor = [System.Drawing.Color]::Empty,
        [switch]$ProfileActiveBadge,
        [string]$ProfileModeBadge = "",
        [switch]$ProfileFavoriteBadge,
        [string]$ActionName = "",
        [System.Drawing.Color]$ActionColor = [System.Drawing.Color]::Empty,
        [object[]]$ActionButtons = @()
    )
    _Ensure-Fonts

    # Layout constants (single source of truth so paint + control placement agree).
    # Tuned for Bahnschrift SemiBold Condensed 15.5pt headline + Cascadia Code 9pt body on Win11 DPI.
    $hasProfileMark = (
        -not [string]::IsNullOrWhiteSpace($ProfileGameGroup) -and
        (Get-Command New-GameBitmap -ErrorAction SilentlyContinue)
    )
    $hasActionMark = (
        -not $hasProfileMark -and
        -not [string]::IsNullOrWhiteSpace($ActionName) -and
        (Get-Command New-ActionBitmap -ErrorAction SilentlyContinue)
    )
    $hasSideMark = ($hasProfileMark -or $hasActionMark)
    $gutterX   = if ($hasSideMark) { 76 } else { 28 }
    $eyebrowY  = 14
    $titleY    = 32
    $ruleY     = 68    # was 62; needs more clearance under the bolder Bahnschrift 15.5pt
    $bodyY     = 82    # was 74; matches rule offset + 14
    $footerH   = 18
    $bodyWidth = $script:ToastWidth - $gutterX - 20
    $toastActions = @($ActionButtons | Where-Object { $_ -and -not [string]::IsNullOrWhiteSpace("$($_.Label)") } | Select-Object -First 2)
    $hasToastActions = ($toastActions.Count -gt 0)
    $buttonH = 24
    $buttonGap = 8

    # Wrap-aware height: use GDI+ MeasureString against the real body font and
    # width so multi-line wrap is sized accurately for Cascadia Code, which is
    # wider per character than serif estimates suggested.
    $bodyHeight = 16
    try {
        $tmpBmp = New-Object System.Drawing.Bitmap 1, 1
        $tmpG   = [System.Drawing.Graphics]::FromImage($tmpBmp)
        $sz     = $tmpG.MeasureString($Message, $script:Font_Body,
            [System.Drawing.SizeF]::new([float]$bodyWidth, 9999.0))
        $tmpG.Dispose(); $tmpBmp.Dispose()
        $bodyHeight = [Math]::Max(16, [int][Math]::Ceiling($sz.Height) + 2)
    } catch {
        $bodyHeight = [Math]::Min(85, [Math]::Max(16,
            [int][Math]::Ceiling($Message.Length / 56.0) * 17))
    }
    $bodyHeightCap = if ($hasToastActions) { 62 } else { 85 }
    $bodyHeight = [Math]::Min($bodyHeight, $bodyHeightCap)

    $actionAreaH = if ($hasToastActions) { $buttonH + $buttonGap } else { 0 }
    $height = $bodyY + $bodyHeight + 14 + $actionAreaH + $footerH + 10
    $height = [Math]::Max($height, 124)
    $height = [Math]::Min($height, 232)

    $form = New-Object System.Windows.Forms.Form
    $form.Text             = ""
    $form.FormBorderStyle  = [System.Windows.Forms.FormBorderStyle]::None
    $form.BackColor        = $script:Penumbra.Ink100
    $form.Size             = New-Object System.Drawing.Size($script:ToastWidth, $height)
    $form.StartPosition    = [System.Windows.Forms.FormStartPosition]::Manual
    $form.TopMost          = $true
    $form.ShowInTaskbar    = $false
    $form.Opacity          = 0

    $capW = $script:ToastWidth
    $capH = $height
    $capMeta = $TypeMeta
    $capChapter = $ChapterText
    # PS hyphenated function lookup inside a deferred event closure can fail
    # when the script was dot-sourced into a non-tray host scope. Pinning a
    # CommandInfo reference up-front and invoking via & avoids the lookup.
    $capPaintFn = Get-Command _Paint-ToastPanel
    $form.Add_Paint({
        param($s, $e)
        & $capPaintFn -g $e.Graphics -Width $capW -Height $capH -Meta $capMeta -ChapterText $capChapter
    }.GetNewClosure())

    $profileImageBox = $null
    $profileImage = $null
    if ($hasSideMark) {
        $markColor = if ($ProfileColor.IsEmpty) { $TypeMeta.Accent } else { $ProfileColor }
        if ($hasActionMark -and -not $ActionColor.IsEmpty) { $markColor = $ActionColor }
        $profileImageBox = New-Object System.Windows.Forms.PictureBox
        $profileImageBox.Location = New-Object System.Drawing.Point(24, 36)
        $profileImageBox.Size = New-Object System.Drawing.Size(36, 36)
        $profileImageBox.SizeMode = [System.Windows.Forms.PictureBoxSizeMode]::Zoom
        $profileImageBox.BackColor = $script:Penumbra.Ink100
        $profileImageBox.Cursor = [System.Windows.Forms.Cursors]::Hand
        $profileImage = if ($hasProfileMark) {
            New-ProfileMarkMedallionBitmap `
                -ProfileGameGroup $ProfileGameGroup `
                -ProfileCategory $ProfileCategory `
                -Color $markColor `
                -ActiveBadge:$ProfileActiveBadge `
                -ModeBadge $ProfileModeBadge `
                -FavoriteBadge:$ProfileFavoriteBadge
        }
        else {
            New-ActionMarkMedallionBitmap -ActionName $ActionName -Color $markColor
        }
        $profileImageBox.Image = $profileImage
        $form.Controls.Add($profileImageBox)
    }

    # Eyebrow (tracked condensed caps in accent, signals the state at a glance).
    # All labels use solid Ink-100 BackColor (matches Form.BackColor) so they
    # composite identically every paint cycle - never any transparency races.
    $eyebrow = New-Object System.Windows.Forms.Label
    $eyebrow.Text      = $TypeMeta.Eyebrow
    $eyebrow.Font      = $script:Font_Eyebrow
    $eyebrow.ForeColor = $TypeMeta.Accent
    $eyebrow.BackColor = $script:Penumbra.Ink100
    $eyebrow.AutoSize  = $false
    $eyebrow.Location  = New-Object System.Drawing.Point($gutterX, $eyebrowY)
    $eyebrow.Size      = New-Object System.Drawing.Size(($bodyWidth - 92), 12)
    $eyebrow.TextAlign = [System.Drawing.ContentAlignment]::MiddleLeft
    $form.Controls.Add($eyebrow)

    # Title (Bahnschrift SemiBold Condensed - geometric HUD type, paper white)
    $titleLabel = New-Object System.Windows.Forms.Label
    $titleLabel.Text         = $Title
    $titleLabel.Font         = $script:Font_Title
    $titleLabel.ForeColor    = $script:Penumbra.Paper
    $titleLabel.BackColor    = $script:Penumbra.Ink100
    $titleLabel.Location     = New-Object System.Drawing.Point($gutterX, $titleY)
    $titleLabel.Size         = New-Object System.Drawing.Size($bodyWidth, 24)
    $titleLabel.AutoEllipsis = $true
    $form.Controls.Add($titleLabel)

    # Phosphor hairline rule under the title (accent-tinted at 70 alpha)
    $rule = New-Object System.Windows.Forms.Panel
    $rule.Location  = New-Object System.Drawing.Point($gutterX, $ruleY)
    $rule.Size      = New-Object System.Drawing.Size($bodyWidth, 1)
    $rule.BackColor = [System.Drawing.Color]::FromArgb(
        255,
        [Math]::Floor($TypeMeta.Accent.R * 0.45 + $script:Penumbra.Ink100.R * 0.55),
        [Math]::Floor($TypeMeta.Accent.G * 0.45 + $script:Penumbra.Ink100.G * 0.55),
        [Math]::Floor($TypeMeta.Accent.B * 0.45 + $script:Penumbra.Ink100.B * 0.55)
    )
    $form.Controls.Add($rule)

    # Body (Cascadia Code, mist)
    $bodyLabel = New-Object System.Windows.Forms.Label
    $bodyLabel.Text      = $Message
    $bodyLabel.Font      = $script:Font_Body
    $bodyLabel.ForeColor = $script:Penumbra.Mist
    $bodyLabel.BackColor = $script:Penumbra.Ink100
    $bodyLabel.Location  = New-Object System.Drawing.Point($gutterX, $bodyY)
    $bodyLabel.Size      = New-Object System.Drawing.Size($bodyWidth, $bodyHeight)
    $form.Controls.Add($bodyLabel)

    $actionControls = @()
    if ($hasToastActions) {
        $buttonY = $bodyY + $bodyHeight + 8
        $buttonW = if ($toastActions.Count -gt 1) {
            [Math]::Max(112, [Math]::Min(146, [int][Math]::Floor(($bodyWidth - $buttonGap) / 2)))
        }
        else {
            [Math]::Max(118, [Math]::Min(156, [int][Math]::Floor($bodyWidth * 0.44)))
        }
        $buttonX = $gutterX

        foreach ($action in $toastActions) {
            $button = New-Object System.Windows.Forms.Button
            $button.Text = "$($action.Label)"
            $button.Tag = $action
            $button.Font = $script:Font_Eyebrow
            $button.ForeColor = $script:Penumbra.Paper
            $button.BackColor = $script:Penumbra.Ink200
            $button.Location = New-Object System.Drawing.Point($buttonX, $buttonY)
            $button.Size = New-Object System.Drawing.Size($buttonW, $buttonH)
            $button.Cursor = [System.Windows.Forms.Cursors]::Hand
            $button.FlatStyle = [System.Windows.Forms.FlatStyle]::Flat
            $button.FlatAppearance.BorderColor = $TypeMeta.Accent
            $button.FlatAppearance.BorderSize = 1
            $button.FlatAppearance.MouseOverBackColor = [System.Drawing.Color]::FromArgb(
                34, $TypeMeta.Accent.R, $TypeMeta.Accent.G, $TypeMeta.Accent.B
            )
            $button.FlatAppearance.MouseDownBackColor = [System.Drawing.Color]::FromArgb(
                52, $TypeMeta.Accent.R, $TypeMeta.Accent.G, $TypeMeta.Accent.B
            )
            $form.Controls.Add($button)
            $actionControls += $button
            $buttonX += $buttonW + $buttonGap
        }
    }

    # Footer (Cascadia Code mono, fog)
    $footerLabel = New-Object System.Windows.Forms.Label
    $footerLabel.Text      = $FooterText
    $footerLabel.Font      = $script:Font_Mono
    $footerLabel.ForeColor = $script:Penumbra.Fog
    $footerLabel.BackColor = $script:Penumbra.Ink100
    $footerLabel.Location  = New-Object System.Drawing.Point($gutterX, ($height - $footerH - 10))
    $footerLabel.Size      = New-Object System.Drawing.Size(($bodyWidth - 70), $footerH)
    $form.Controls.Add($footerLabel)

    # Dismiss hairline (full width, recedes right -> left over Duration)
    $dismissHost = New-Object System.Windows.Forms.Panel
    $dismissHost.Location  = New-Object System.Drawing.Point(6, ($height - 1))
    $dismissHost.Size      = New-Object System.Drawing.Size(($script:ToastWidth - 6), 1)
    $dismissHost.BackColor = $script:Penumbra.Ink300
    $form.Controls.Add($dismissHost)

    return @{
        Form        = $form
        TitleLabel  = $titleLabel
        BodyLabel   = $bodyLabel
        FooterLabel = $footerLabel
        EyebrowLabel= $eyebrow
        DismissHost = $dismissHost
        ProfileImageBox = $profileImageBox
        ProfileImage = $profileImage
        ActionButtons = @($actionControls)
        Height      = $height
    }
}

# ============================================================================
# PUBLIC: Show-ThemedToast
# ============================================================================

function Show-ThemedToast {
    <#
    .SYNOPSIS
    Shows a Penumbra editorial notification. Supports stacking, queueing, dedup.

    .PARAMETER Title
    Toast headline. If the generic "computa" brand prefix is detected, a
    contextual title is synthesized from the message body instead - the
    eyebrow above already carries the brand and state.

    .PARAMETER Message
    Body text (up to ~3 wrapped lines before truncation).

    .PARAMETER Type
    Info | Success | Warning | Error - controls accent + eyebrow tag + priority.

    .PARAMETER Duration
    Lifetime in milliseconds before auto-dismiss (default 4500).

    .PARAMETER MetaText
    Optional metadata appended to the footer after the timestamp (e.g. profile id).
    #>
    param(
        [string]$Title = "computa",
        [string]$Message = "",
        [ValidateSet("Info","Warning","Error","Success")]
        [string]$Type = "Info",
        [int]$Duration = 4500,
        [string]$MetaText = "",
        # When the toast is fired in response to an explicit user action (clicking
        # "Apply" in the tray menu, hitting "Restore", etc.) the dedup window
        # silently swallowing the popup makes the UI feel dead — the user clicked,
        # nothing happened. Callers can pass -BypassDedup to acknowledge that the
        # action is intentional and should always surface a toast.
        [switch]$BypassDedup,
        [string]$ProfileGameGroup = "",
        [string]$ProfileCategory = "Other",
        [System.Drawing.Color]$ProfileColor = [System.Drawing.Color]::Empty,
        [switch]$ProfileActiveBadge,
        [string]$ProfileModeBadge = "",
        [switch]$ProfileFavoriteBadge,
        [string]$ActionName = "",
        [System.Drawing.Color]$ActionColor = [System.Drawing.Color]::Empty,
        [object[]]$ActionButtons = @()
    )

    try {
        $typeMeta  = _Get-ToastTypeMeta -Type $Type
        $realTitle = _Derive-ToastTitle -RawTitle $Title -Message $Message -Type $Type
        $realBody  = _Derive-ToastBody  -Message $Message
        $footer    = _Format-ToastFooter -Meta $MetaText
        $key       = "$Type|$realTitle|$realBody"

        $nowMs = [DateTimeOffset]::Now.ToUnixTimeMilliseconds()
        if (-not $BypassDedup -and $script:ToastDedupMap.ContainsKey($key)) {
            $last = $script:ToastDedupMap[$key]
            if (($nowMs - $last) -lt $script:ToastDedupWindowMs) {
                if (Get-Command Write-TrayLog -ErrorAction SilentlyContinue) {
                    Write-TrayLog "Toast dedup: suppressed '$realTitle' within ${script:ToastDedupWindowMs}ms" -Level "INFO"
                }
                return
            }
        }
        _Evict-DedupMap
        $script:ToastDedupMap[$key] = $nowMs

        if (Get-Command Write-TrayLog -ErrorAction SilentlyContinue) {
            Write-TrayLog "Toast[$Type] $realTitle :: $Message" -Level "INFO"
        }

        if ($script:ActiveToasts.Count -ge $script:ToastMaxVisible) {
            $queueItem = @{
                Title = $realTitle; Message = $realBody; Type = $Type
                Duration = $Duration; MetaText = $MetaText
                ProfileGameGroup = $ProfileGameGroup; ProfileCategory = $ProfileCategory
                ProfileColor = $ProfileColor; ProfileActiveBadge = [bool]$ProfileActiveBadge
                ProfileModeBadge = $ProfileModeBadge; ProfileFavoriteBadge = [bool]$ProfileFavoriteBadge
                ActionName = $ActionName; ActionColor = $ActionColor
                ActionButtons = @($ActionButtons)
            }
            # Error preempts the oldest Info/Success so critical signals always surface
            if ($typeMeta.Priority -ge 4) {
                $bumpIndex = -1
                for ($i = 0; $i -lt $script:ActiveToasts.Count; $i++) {
                    $p = (_Get-ToastTypeMeta -Type $script:ActiveToasts[$i].Type).Priority
                    if ($p -le 2) { $bumpIndex = $i; break }
                }
                if ($bumpIndex -ge 0) {
                    _Dismiss-ActiveToast -Toast $script:ActiveToasts[$bumpIndex] -Fast
                } else {
                    if ($script:ToastQueue.Count -ge $script:ToastQueueMaxSize) {
                        if (Get-Command Write-TrayLog -ErrorAction SilentlyContinue) {
                            Write-TrayLog "Toast queue at cap ($($script:ToastQueueMaxSize)); dropping '$realTitle'" -Level "WARN"
                        }
                        return
                    }
                    $script:ToastQueue.Enqueue($queueItem)
                    return
                }
            } else {
                if ($script:ToastQueue.Count -ge $script:ToastQueueMaxSize) {
                    if (Get-Command Write-TrayLog -ErrorAction SilentlyContinue) {
                        Write-TrayLog "Toast queue at cap ($($script:ToastQueueMaxSize)); dropping '$realTitle'" -Level "WARN"
                    }
                    return
                }
                $script:ToastQueue.Enqueue($queueItem)
                return
            }
        }

        _Spawn-Toast -Title $realTitle -Message $realBody -Type $Type `
            -TypeMeta $typeMeta -FooterText $footer -Duration $Duration -Key $key `
            -ProfileGameGroup $ProfileGameGroup -ProfileCategory $ProfileCategory `
            -ProfileColor $ProfileColor -ProfileActiveBadge:$ProfileActiveBadge `
            -ProfileModeBadge $ProfileModeBadge -ProfileFavoriteBadge:$ProfileFavoriteBadge `
            -ActionName $ActionName -ActionColor $ActionColor `
            -ActionButtons @($ActionButtons)
    } catch {
        if (Get-Command Write-TrayLog -ErrorAction SilentlyContinue) {
            Write-TrayLog "Show-ThemedToast failed: $($_.Exception.Message)" -Level "ERROR"
        }
    }
}

function _Spawn-Toast {
    param(
        [string]$Title, [string]$Message, [string]$Type,
        [hashtable]$TypeMeta, [string]$FooterText, [int]$Duration, [string]$Key,
        [string]$ProfileGameGroup = "",
        [string]$ProfileCategory = "Other",
        [System.Drawing.Color]$ProfileColor = [System.Drawing.Color]::Empty,
        [switch]$ProfileActiveBadge,
        [string]$ProfileModeBadge = "",
        [switch]$ProfileFavoriteBadge,
        [string]$ActionName = "",
        [System.Drawing.Color]$ActionColor = [System.Drawing.Color]::Empty,
        [object[]]$ActionButtons = @()
    )

    $script:ToastChapterSeq++
    $chapterText = _Format-ChapterMark -Seq $script:ToastChapterSeq

    $built = _Build-ToastForm `
        -Title $Title -Message $Message -FooterText $FooterText `
        -TypeMeta $TypeMeta -ChapterText $chapterText `
        -ProfileGameGroup $ProfileGameGroup -ProfileCategory $ProfileCategory `
        -ProfileColor $ProfileColor -ProfileActiveBadge:$ProfileActiveBadge `
        -ProfileModeBadge $ProfileModeBadge -ProfileFavoriteBadge:$ProfileFavoriteBadge `
        -ActionName $ActionName -ActionColor $ActionColor `
        -ActionButtons @($ActionButtons)
    $form = $built.Form

    $slotIndex = $script:ActiveToasts.Count
    $targetY = _Compute-ToastTargetY -IndexFromBottom $slotIndex -Height $built.Height
    $screen  = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
    $targetX = $screen.Right - $script:ToastWidth - $script:ToastRightMargin
    # Slide-in start: +20px right of target, opacity 0
    $form.Location = New-Object System.Drawing.Point(($targetX + 20), $targetY)

    $toast = @{
        Form           = $form
        TitleLabel     = $built.TitleLabel
        BodyLabel      = $built.BodyLabel
        FooterLabel    = $built.FooterLabel
        EyebrowLabel   = $built.EyebrowLabel
        DismissHost    = $built.DismissHost
        ProfileImageBox= $built.ProfileImageBox
        ProfileImage   = $built.ProfileImage
        ActionButtons  = @($built.ActionButtons)
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
        Dismissing     = $false
    }

    # Click-anywhere-to-dismiss (the whole card is the affordance)
    $closeHandler = { _Dismiss-ActiveToast -Toast $toast }.GetNewClosure()
    $form.Add_Click($closeHandler)
    $built.TitleLabel.Add_Click($closeHandler)
    $built.BodyLabel.Add_Click($closeHandler)
    $built.FooterLabel.Add_Click($closeHandler)
    $built.EyebrowLabel.Add_Click($closeHandler)
    if ($built.ProfileImageBox) { $built.ProfileImageBox.Add_Click($closeHandler) }
    foreach ($button in @($built.ActionButtons)) {
        if (-not $button) { continue }
        $button.Add_Click({
            param($s, $e)
            try {
                if (Get-Command Invoke-TrayToastAction -ErrorAction SilentlyContinue) {
                    Invoke-TrayToastAction -Action $s.Tag
                }
            } catch {
                if (Get-Command Write-TrayLog -ErrorAction SilentlyContinue) {
                    Write-TrayLog "Toast action failed: $($_.Exception.Message)" -Level "ERROR"
                }
            }
            _Dismiss-ActiveToast -Toast $toast -Fast
        }.GetNewClosure())
    }

    $form.Show()

    # DWM dark mode + rounded corners + accent-tinted border
    try {
        if ("DwmHelper" -as [type]) {
            Apply-DwmWindowEffects -Form $form -CornerStyle 3 -BorderColorRGB @(
                $TypeMeta.Accent.R, $TypeMeta.Accent.G, $TypeMeta.Accent.B
            )
        }
    } catch {}

    # Explicit Win32 TOPMOST assertion - beats Discord and other competing topmost windows
    try {
        if ("AbsoZOrder" -as [type]) { [AbsoZOrder]::ForceTopmost($form.Handle) }
    } catch {}

    $script:ActiveToasts.Add($toast) | Out-Null

    _Animate-ToastEntry -Toast $toast -TargetX $targetX
    _Start-DismissHairline -Toast $toast

    # Lifetime auto-dismiss
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
    # Frame count derived from monitor refresh: ~280ms wall clock regardless
    # of hz, but the curve is sampled at refresh rate so it feels native on
    # 144/240/300Hz panels rather than always rendering at 60.
    $steps = [Math]::Max(12, [int](280 / $script:FrameInterval))
    $step  = [ref]0
    $timer = New-Object System.Windows.Forms.Timer
    $timer.Interval = $script:FrameInterval
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
            $x = [int]($local.TargetX + ((1 - $eased) * 20))
            $tt.Form.Left = $x
            $tt.Form.Opacity = [Math]::Min(0.98, $eased * 0.98)
            if ($raw -ge 1) { $this.Stop(); $this.Dispose() }
        } catch { try { $this.Stop(); $this.Dispose() } catch {} }
    })
    $Toast.SlideTimer = $timer
    $timer.Start()
}

function _Start-DismissHairline {
    <#
    .SYNOPSIS
    Recedes the 1px dismiss line from the right edge to the left over Duration.
    Replaces the v3 segmented dismiss bar with a single calm hairline.
    #>
    param([hashtable]$Toast)
    # Local name is $bar - $host is a read-only PS automatic and assigning to it errors.
    $bar = $Toast.DismissHost
    $accent = $Toast.Accent

    # Establish the full hairline at full accent at the start
    $bar.BackColor = $accent

    $startW = $bar.Width
    # Frame budget scales with monitor refresh: shorter ticks on 144/240Hz panels.
    $frames = [Math]::Min(64, [int]($Toast.Duration / [Math]::Max($script:FrameInterval, 30)))
    if ($frames -lt 16) { $frames = 16 }
    $tickMs = [Math]::Max($script:FrameInterval, [int]($Toast.Duration / $frames))

    $interval = New-Object System.Windows.Forms.Timer
    $interval.Interval = $tickMs
    $state = @{ Toast = $Toast; Frame = [ref]0; Frames = $frames; StartW = $startW; Timer = $interval }
    $interval.Tag = $state
    $interval.Add_Tick({
        try {
            $local = $this.Tag
            $tt = $local.Toast
            if (-not $tt.Form -or $tt.Form.IsDisposed) { $this.Stop(); $this.Dispose(); return }
            $local.Frame.Value++
            $raw = [double]$local.Frame.Value / $local.Frames
            if ($raw -ge 1) { $raw = 1 }
            # The hairline recedes from the right - shrink width while keeping left edge fixed.
            $newW = [int]($local.StartW * (1 - $raw))
            if ($newW -lt 0) { $newW = 0 }
            $tt.DismissHost.Size = New-Object System.Drawing.Size($newW, 1)
            if ($raw -ge 1) { $this.Stop(); $this.Dispose() }
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

    # Same 220ms wall clock for the slide-out, with frames sampled at refresh
    $fastMs = 110; $slowMs = 220
    $durMs = if ($Fast) { $fastMs } else { $slowMs }
    $steps = [Math]::Max(6, [int]($durMs / $script:FrameInterval))
    $step  = [ref]0
    $fade  = New-Object System.Windows.Forms.Timer
    $fade.Interval = $script:FrameInterval
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
            # Ease-in cubic on the way out (settled feel, not snappy)
            $eased = [Math]::Pow($raw, 2)
            $tt.Form.Top = [int]($local.StartY - ($eased * 10))
            $tt.Form.Opacity = [Math]::Max(0, 0.98 - $eased * 0.98)
            if ($raw -ge 1) {
                $this.Stop(); $this.Dispose()
                try { $tt.Form.Hide() } catch {}
                if ($tt.ProfileImageBox) {
                    try { $tt.ProfileImageBox.Image = $null } catch {}
                }
                if ($tt.ProfileImage) {
                    try { $tt.ProfileImage.Dispose() } catch {}
                    $tt.ProfileImage = $null
                }
                try { $tt.Form.Close() } catch {}
                try { $tt.Form.Dispose() } catch {}
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
        $footer = _Format-ToastFooter -Meta $q.MetaText
        $key = "$($q.Type)|$($q.Title)|$($q.Message)"
        _Spawn-Toast -Title $q.Title -Message $q.Message -Type $q.Type `
            -TypeMeta $typeMeta -FooterText $footer -Duration $q.Duration -Key $key `
            -ProfileGameGroup $q.ProfileGameGroup -ProfileCategory $q.ProfileCategory `
            -ProfileColor $q.ProfileColor -ProfileActiveBadge:([bool]$q.ProfileActiveBadge) `
            -ProfileModeBadge $q.ProfileModeBadge -ProfileFavoriteBadge:([bool]$q.ProfileFavoriteBadge) `
            -ActionName $q.ActionName -ActionColor $q.ActionColor `
            -ActionButtons @($q.ActionButtons)
    }
}

# ============================================================================
# PUBLIC: Close-ThemedToast (clears all)
# ============================================================================

function Close-ThemedToast {
    <#
    .SYNOPSIS
    Dismisses every active toast and empties the pending queue.
    #>
    try { $script:ToastQueue.Clear() } catch {}
    $snapshot = @()
    foreach ($t in $script:ActiveToasts) { $snapshot += ,$t }
    foreach ($t in $snapshot) {
        try { _Dismiss-ActiveToast -Toast $t -Fast } catch {}
    }
}

# ============================================================================
# PROGRESS OVERLAY (Penumbra chassis: same surface system as toasts)
# ============================================================================

$script:ProgressForm           = $null
$script:ProgressStepLabel      = $null
$script:ProgressTitleLabel     = $null
$script:ProgressTrack          = $null
$script:ProgressFill           = $null
$script:ProgressElapsedLabel   = $null
$script:ProgressTimer          = $null
$script:ProgressElapsedTimer   = $null
$script:ProgressStartTime      = $null
$script:ProgressAngle          = 0
$script:ProgressShimmerOffset  = -60
$script:ProgressProfileImageBox= $null
$script:ProgressProfileImage   = $null
$script:ProgressDismissButton  = $null
$script:ProgressDismissImage   = $null

function Show-ProgressOverlay {
    <#
    .SYNOPSIS
    Shows a Penumbra-styled progress panel during long-running profile apply.

    .PARAMETER Title    Headline (e.g. "Applying Rivals 2: Online")
    .PARAMETER StepText Current step text
    #>
    param(
        [string]$Title = "Applying profile",
        [string]$StepText = "Initializing...",
        [string]$ProfileGameGroup = "",
        [string]$ProfileCategory = "Other",
        [System.Drawing.Color]$ProfileColor = [System.Drawing.Color]::Empty,
        [switch]$ProfileActiveBadge,
        [string]$ProfileModeBadge = "",
        [switch]$ProfileFavoriteBadge,
        [string]$ActionName = "",
        [System.Drawing.Color]$ActionColor = [System.Drawing.Color]::Empty
    )
    Close-ProgressOverlay
    _Ensure-Fonts

    $hasProfileMark = (
        -not [string]::IsNullOrWhiteSpace($ProfileGameGroup) -and
        (Get-Command New-GameBitmap -ErrorAction SilentlyContinue)
    )
    $hasActionMark = (
        -not $hasProfileMark -and
        -not [string]::IsNullOrWhiteSpace($ActionName) -and
        (Get-Command New-ActionBitmap -ErrorAction SilentlyContinue)
    )
    $hasSideMark = ($hasProfileMark -or $hasActionMark)
    $accent = if ($hasProfileMark -and -not $ProfileColor.IsEmpty) {
        $ProfileColor
    }
    elseif ($hasActionMark -and -not $ActionColor.IsEmpty) {
        $ActionColor
    }
    else {
        $script:Penumbra.Lagoon
    }
    $width  = if ($hasSideMark) { 500 } else { 460 }
    $height = 156
    $gutter = if ($hasSideMark) { 78 } else { 26 }

    $form = New-Object System.Windows.Forms.Form
    $form.Text             = ""
    $form.FormBorderStyle  = [System.Windows.Forms.FormBorderStyle]::None
    $form.BackColor        = $script:Penumbra.Ink100
    $form.Size             = New-Object System.Drawing.Size($width, $height)
    $form.StartPosition    = [System.Windows.Forms.FormStartPosition]::Manual
    $form.TopMost          = $true
    $form.ShowInTaskbar    = $false
    $form.Opacity          = 0

    # Progress overlay lives in the BOTTOM-left corner so it never collides
    # with the toast stack (bottom-right). Bottom-left also dodges IDE / browser
    # title-bar chrome that other top-right candidates conflict with.
    $screen = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
    $form.Location = New-Object System.Drawing.Point(
        ($screen.Left + 18),
        ($screen.Bottom - $height - 18)
    )

    $capAccent  = $accent
    $capW       = $width
    $capH       = $height
    # Pin every script-scope value the Paint closure touches into local
    # captures *before* GetNewClosure. WinForms invokes Add_Paint on a
    # deferred WndProc dispatch where $script: hashtable lookups have
    # occasionally returned $null on first paint — passing $null to
    # SolidBrush(Color) raises "constructor not found" and WinForms then
    # renders the broken-control placeholder (white panel, red diagonal X).
    $capInk100  = $script:Penumbra.Ink100
    $capFog     = $script:Penumbra.Fog
    $capHzText  = $script:HzBadgeText
    $capFontTag = $script:Font_Tag
    $capHasSideMark = $hasSideMark
    $form.BackColor = $capInk100
    $form.Add_Paint({
        param($s, $e)
        # Belt-and-suspenders: if anything in the chrome paint throws, eat
        # the exception and at least leave a solid ink fill on the form.
        # An unhandled throw here makes WinForms render the broken-control
        # placeholder (white panel + diagonal red X) over the overlay even
        # though all the child labels paint fine on top of it.
        try {
            $g = $e.Graphics
            $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
            $g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::ClearTypeGridFit

            # 1) Solid ink base (matches label backgrounds so labels blend invisibly).
            #    Scanlines + grain removed - see _Paint-ToastPanel for the rationale.
            $baseBrush = New-Object System.Drawing.SolidBrush($capInk100)
            $g.FillRectangle($baseBrush, 0, 0, $capW, $capH)
            $baseBrush.Dispose()

            # 4) Outline
            $outlinePen = New-Object System.Drawing.Pen(
                [System.Drawing.Color]::FromArgb(80, $capAccent.R, $capAccent.G, $capAccent.B), 1
            )
            $g.DrawRectangle($outlinePen, 0, 0, ($capW - 1), ($capH - 1))
            $outlinePen.Dispose()

            # 5) Left accent rail (6px) with tick perforations
            $strokeBrush = New-Object System.Drawing.SolidBrush($capAccent)
            $g.FillRectangle($strokeBrush, 0, 0, 6, $capH)
            $strokeBrush.Dispose()
            $featherBrush = New-Object System.Drawing.SolidBrush(
                [System.Drawing.Color]::FromArgb(80, $capAccent.R, $capAccent.G, $capAccent.B)
            )
            $g.FillRectangle($featherBrush, 6, 0, 1, $capH)
            $featherBrush.Dispose()
            $tickBrush = New-Object System.Drawing.SolidBrush($capInk100)
            for ($ty = 14; $ty -lt ($capH - 6); $ty += 22) {
                $g.FillRectangle($tickBrush, 0, $ty, 6, 1)
            }
            $tickBrush.Dispose()

            # Profile/action overlays get a live beacon behind the medallion.
            # It uses the existing ProgressAngle timer, so there is no extra
            # animation loop.
            if ($capHasSideMark) {
                $markWave = ([Math]::Sin($script:ProgressAngle / 24.0) + 1.0) / 2.0
                $markHaloAlpha = [int](28 + (24 * $markWave))
                $markHaloBrush = New-Object System.Drawing.SolidBrush(
                    [System.Drawing.Color]::FromArgb($markHaloAlpha, $capAccent.R, $capAccent.G, $capAccent.B)
                )
                $g.FillEllipse($markHaloBrush, 19, 37, 50, 50)
                $markHaloBrush.Dispose()

                $markOrbitPen = New-Object System.Drawing.Pen(
                    [System.Drawing.Color]::FromArgb([int](118 + (70 * $markWave)), $capAccent.R, $capAccent.G, $capAccent.B), 1.35
                )
                $markOrbitPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
                $markOrbitPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
                $g.DrawArc($markOrbitPen, 20, 38, 48, 48, (($script:ProgressAngle + 205) % 360), 84)
                $markOrbitPen.Dispose()

                $markLinkPen = New-Object System.Drawing.Pen(
                    [System.Drawing.Color]::FromArgb([int](58 + (40 * $markWave)), $capAccent.R, $capAccent.G, $capAccent.B), 1.0
                )
                $markLinkPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
                $markLinkPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
                $g.DrawLine($markLinkPen, 64, 62, 74, 62)
                $g.DrawLine($markLinkPen, 64, 70, 70, 70)
                $markLinkPen.Dispose()
            }

            # 6) L-shaped corner brackets (TR + BL + BR)
            $bracketLen = 10
            $bracketPen = New-Object System.Drawing.Pen($capAccent, 1.6)
            $g.DrawLine($bracketPen, ($capW - $bracketLen - 2), 2, ($capW - 2), 2)
            $g.DrawLine($bracketPen, ($capW - 2), 2, ($capW - 2), ($bracketLen + 2))
            $g.DrawLine($bracketPen, ($capW - 2), ($capH - $bracketLen - 2), ($capW - 2), ($capH - 2))
            $g.DrawLine($bracketPen, ($capW - $bracketLen - 2), ($capH - 2), ($capW - 2), ($capH - 2))
            $g.DrawLine($bracketPen, 6, ($capH - 2), ($bracketLen + 6), ($capH - 2))
            $bracketPen.Dispose()

            # 7) Rotating quarter-arc spinner (phosphor) in the top-right
            $cx = $capW - 32; $cy = 24
            $arcPen = New-Object System.Drawing.Pen($capAccent, 1.8)
            $arcPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
            $arcPen.EndCap   = [System.Drawing.Drawing2D.LineCap]::Round
            $g.DrawArc($arcPen, ($cx - 9), ($cy - 9), 18, 18, $script:ProgressAngle, 130)
            $arcDimPen = New-Object System.Drawing.Pen(
                [System.Drawing.Color]::FromArgb(70, $capAccent.R, $capAccent.G, $capAccent.B), 1.2
            )
            $g.DrawArc($arcDimPen, ($cx - 9), ($cy - 9), 18, 18, ($script:ProgressAngle + 180), 80)
            $arcPen.Dispose()
            $arcDimPen.Dispose()

            # 8) Hz badge in the bottom-right corner (gamer flex)
            $hzBrush = New-Object System.Drawing.SolidBrush($capFog)
            $hzSize = $g.MeasureString($capHzText, $capFontTag)
            $g.DrawString($capHzText, $capFontTag, $hzBrush,
                ($capW - $hzSize.Width - 16), ($capH - $hzSize.Height - 10))
            $hzBrush.Dispose()
        } catch {
            try {
                $fallback = New-Object System.Drawing.SolidBrush(
                    [System.Drawing.Color]::FromArgb(255, 12, 16, 20)
                )
                $e.Graphics.FillRectangle($fallback, 0, 0, $capW, $capH)
                $fallback.Dispose()
            } catch {}
        }
    }.GetNewClosure())

    $profileImageBox = $null
    $profileImage = $null
    if ($hasSideMark) {
        $profileImageBox = New-Object System.Windows.Forms.PictureBox
        $profileImageBox.Location = New-Object System.Drawing.Point(26, 44)
        $profileImageBox.Size = New-Object System.Drawing.Size(36, 36)
        $profileImageBox.SizeMode = [System.Windows.Forms.PictureBoxSizeMode]::Zoom
        $profileImageBox.BackColor = $script:Penumbra.Ink100
        if ($hasProfileMark) {
            $profileImage = New-ProfileMarkMedallionBitmap `
                -ProfileGameGroup $ProfileGameGroup `
                -ProfileCategory $ProfileCategory `
                -Color $accent `
                -ActiveBadge:$ProfileActiveBadge `
                -ModeBadge $ProfileModeBadge `
                -FavoriteBadge:$ProfileFavoriteBadge
        }
        else {
            $profileImage = New-ActionMarkMedallionBitmap -ActionName $ActionName -Color $accent
        }
        $profileImageBox.Image = $profileImage
        $form.Controls.Add($profileImageBox)
    }

    # Eyebrow
    # Eyebrow (tracked condensed caps in phosphor)
    $eyebrow = New-Object System.Windows.Forms.Label
    $eyebrow.Text      = "OPERATION / IN PROGRESS"
    $eyebrow.Font      = $script:Font_Eyebrow
    $eyebrow.ForeColor = $accent
    $eyebrow.BackColor = $script:Penumbra.Ink100
    $eyebrow.AutoSize  = $false
    $eyebrow.Location  = New-Object System.Drawing.Point($gutter, 14)
    $eyebrow.Size      = New-Object System.Drawing.Size(($width - $gutter - 80), 12)
    $form.Controls.Add($eyebrow)

    # Title (Bahnschrift SemiBold Condensed)
    $titleLabel = New-Object System.Windows.Forms.Label
    $titleLabel.Text         = $Title
    $titleLabel.Font         = $script:Font_Title
    $titleLabel.ForeColor    = $script:Penumbra.Paper
    $titleLabel.BackColor    = $script:Penumbra.Ink100
    $titleLabel.Location     = New-Object System.Drawing.Point($gutter, 32)
    $titleLabel.Size         = New-Object System.Drawing.Size(($width - $gutter - 18), 24)
    $titleLabel.AutoEllipsis = $true
    $form.Controls.Add($titleLabel)

    # Phosphor hairline rule under the title
    $rule = New-Object System.Windows.Forms.Panel
    $rule.Location  = New-Object System.Drawing.Point($gutter, 62)
    $rule.Size      = New-Object System.Drawing.Size(($width - $gutter - 18), 1)
    $rule.BackColor = [System.Drawing.Color]::FromArgb(
        255,
        [Math]::Floor($accent.R * 0.45 + $script:Penumbra.Ink100.R * 0.55),
        [Math]::Floor($accent.G * 0.45 + $script:Penumbra.Ink100.G * 0.55),
        [Math]::Floor($accent.B * 0.45 + $script:Penumbra.Ink100.B * 0.55)
    )
    $form.Controls.Add($rule)

    # Step text (Cascadia Code mist)
    $stepLabel = New-Object System.Windows.Forms.Label
    $stepLabel.Text      = $StepText
    $stepLabel.Font      = $script:Font_Body
    $stepLabel.ForeColor = $script:Penumbra.Mist
    $stepLabel.BackColor = $script:Penumbra.Ink100
    $stepLabel.Location  = New-Object System.Drawing.Point($gutter, 72)
    $stepLabel.Size      = New-Object System.Drawing.Size(($width - $gutter - 18), 18)
    $form.Controls.Add($stepLabel)

    # Hairline progress track + sweeping highlight
    $progressTrack = New-Object System.Windows.Forms.Panel
    $progressTrack.Location  = New-Object System.Drawing.Point($gutter, 100)
    $progressTrack.Size      = New-Object System.Drawing.Size(($width - $gutter - 18), 2)
    $progressTrack.BackColor = $script:Penumbra.Ink300

    $progressFill = New-Object System.Windows.Forms.Panel
    $progressFill.Location  = New-Object System.Drawing.Point(0, 0)
    $progressFill.Size      = New-Object System.Drawing.Size(0, 2)
    $progressFill.BackColor = [System.Drawing.Color]::Transparent
    # Same null-safe capture pattern as the form Paint closure above.
    $capProgressAccent = $accent
    $progressFill.Add_Paint({
        param($s, $e)
        if ($s.Width -le 1) { return }
        $g = $e.Graphics
        try {
            $fill = New-Object System.Drawing.Drawing2D.LinearGradientBrush(
                (New-Object System.Drawing.Rectangle(0, 0, [Math]::Max(2, $s.Width), $s.Height)),
                [System.Drawing.Color]::FromArgb(180, $capProgressAccent.R, $capProgressAccent.G, $capProgressAccent.B),
                $capProgressAccent,
                [System.Drawing.Drawing2D.LinearGradientMode]::Horizontal
            )
            $g.FillRectangle($fill, 0, 0, $s.Width, $s.Height)
            $fill.Dispose()
        } catch {
            $solid = New-Object System.Drawing.SolidBrush($capProgressAccent)
            $g.FillRectangle($solid, 0, 0, $s.Width, $s.Height)
            $solid.Dispose()
        }
        $shX = $script:ProgressShimmerOffset
        if ($shX -lt $s.Width) {
            $sh = New-Object System.Drawing.SolidBrush(
                [System.Drawing.Color]::FromArgb(80, 255, 255, 255)
            )
            $g.FillRectangle($sh, $shX, 0, [Math]::Min(60, $s.Width - $shX), $s.Height)
            $sh.Dispose()
        }
    }.GetNewClosure())
    $progressTrack.Controls.Add($progressFill)
    $form.Controls.Add($progressTrack)

    # Elapsed time (Cascadia Code mono, fog) + icon-backed dismiss action.
    $elapsedLabel = New-Object System.Windows.Forms.Label
    $elapsedLabel.Text      = "0.0s"
    $elapsedLabel.ForeColor = $script:Penumbra.Fog
    $elapsedLabel.Font      = $script:Font_Mono
    $elapsedLabel.Location  = New-Object System.Drawing.Point($gutter, 120)
    $elapsedLabel.Size      = New-Object System.Drawing.Size(80, 16)
    $elapsedLabel.BackColor = $script:Penumbra.Ink100
    $form.Controls.Add($elapsedLabel)

    $dismissImage = $null
    if (Get-Command New-ActionBitmap -ErrorAction SilentlyContinue) {
        $dismissImage = New-ActionBitmap -Action "Close" -Color $script:Penumbra.Fog
    }
    $cancelButton = New-Object System.Windows.Forms.Button
    $cancelButton.Text      = "DISMISS"
    $cancelButton.ForeColor = $script:Penumbra.Fog
    $cancelButton.Font      = $script:Font_Eyebrow
    $cancelButton.Location  = New-Object System.Drawing.Point(($width - 114), 116)
    $cancelButton.Size      = New-Object System.Drawing.Size(92, 26)
    $cancelButton.BackColor = $script:Penumbra.Ink100
    $cancelButton.Cursor    = [System.Windows.Forms.Cursors]::Hand
    $cancelButton.FlatStyle = [System.Windows.Forms.FlatStyle]::Flat
    $cancelButton.FlatAppearance.BorderSize = 0
    $cancelButton.FlatAppearance.MouseOverBackColor = [System.Drawing.Color]::FromArgb(22, $script:Penumbra.Coral.R, $script:Penumbra.Coral.G, $script:Penumbra.Coral.B)
    $cancelButton.FlatAppearance.MouseDownBackColor = [System.Drawing.Color]::FromArgb(36, $script:Penumbra.Coral.R, $script:Penumbra.Coral.G, $script:Penumbra.Coral.B)
    $cancelButton.Image = $dismissImage
    $cancelButton.ImageAlign = [System.Drawing.ContentAlignment]::MiddleLeft
    $cancelButton.TextAlign = [System.Drawing.ContentAlignment]::MiddleRight
    $cancelButton.TextImageRelation = [System.Windows.Forms.TextImageRelation]::ImageBeforeText
    $cancelButton.Padding = New-Object System.Windows.Forms.Padding(6, 0, 6, 0)
    $cancelButton.UseVisualStyleBackColor = $false
    $cancelButton.Add_Click({ Close-ProgressOverlay })
    $cancelButton.Add_MouseEnter({ $this.ForeColor = $script:Penumbra.Coral })
    $cancelButton.Add_MouseLeave({ $this.ForeColor = $script:Penumbra.Fog })
    $form.Controls.Add($cancelButton)
    $script:ProgressDismissButton = $cancelButton
    $script:ProgressDismissImage = $dismissImage

    # Animation timer at monitor refresh rate (8ms floor for WinForms)
    $timer = New-Object System.Windows.Forms.Timer
    $script:ProgressTimer = $timer
    $timer.Interval = $script:FrameInterval
    $script:ProgressAngle = 0
    $script:ProgressShimmerOffset = -60
    # Step the spinner so it completes ~1 revolution per 1.4s regardless of refresh
    $angleStep = [Math]::Max(2, [int](360 * $script:FrameInterval / 1400))
    $timer.Tag = $angleStep
    $timer.Add_Tick({
        try {
            # Form went away outside Close-ProgressOverlay (e.g. window
            # forcibly destroyed): self-dispose so we don't leak a 125 Hz
            # timer leaning on a dead form ref.
            if (-not $script:ProgressForm -or $script:ProgressForm.IsDisposed) {
                $this.Stop(); $this.Dispose(); return
            }
            $script:ProgressAngle = ($script:ProgressAngle + $this.Tag) % 360
            if ($script:ProgressFill) {
                $barWidth = 120
                $maxX = $script:ProgressTrack.Width
                $cycle = ($script:ProgressAngle * 2) % ($maxX * 2)
                $x = if ($cycle -lt $maxX) { $cycle } else { $maxX * 2 - $cycle }
                $x = [int]$x
                if (($x + $barWidth) -gt $maxX) { $barWidth = $maxX - $x }
                $script:ProgressFill.Location = New-Object System.Drawing.Point($x, 0)
                $script:ProgressFill.Size = New-Object System.Drawing.Size([Math]::Max(1, $barWidth), 2)
                $script:ProgressShimmerOffset += 4
                if ($script:ProgressShimmerOffset -gt $barWidth + 60) { $script:ProgressShimmerOffset = -60 }
                $script:ProgressFill.Invalidate()
                $script:ProgressForm.Invalidate()
            }
        } catch { try { $this.Stop(); $this.Dispose() } catch {} }
    })
    $timer.Start()

    $script:ProgressStartTime = Get-Date
    $elapsedTimer = New-Object System.Windows.Forms.Timer
    $elapsedTimer.Interval = 100
    $capturedLabel = $elapsedLabel
    $elapsedTimer.Add_Tick({
        try {
            if (-not $capturedLabel -or $capturedLabel.IsDisposed) {
                $this.Stop(); $this.Dispose(); return
            }
            $s = ((Get-Date) - $script:ProgressStartTime).TotalSeconds
            $capturedLabel.Text = ("{0:N1}s" -f $s)
        } catch { try { $this.Stop(); $this.Dispose() } catch {} }
    })
    $elapsedTimer.Start()
    $script:ProgressElapsedTimer = $elapsedTimer

    $script:ProgressForm         = $form
    $script:ProgressStepLabel    = $stepLabel
    $script:ProgressTitleLabel   = $titleLabel
    $script:ProgressTrack        = $progressTrack
    $script:ProgressFill         = $progressFill
    $script:ProgressElapsedLabel = $elapsedLabel
    $script:ProgressProfileImageBox = $profileImageBox
    $script:ProgressProfileImage = $profileImage

    $form.Show()

    try {
        if ("DwmHelper" -as [type]) {
            Apply-DwmWindowEffects -Form $form -CornerStyle 3 -BorderColorRGB @(
                $accent.R, $accent.G, $accent.B
            )
        }
    } catch {}

    # Explicit Win32 TOPMOST + periodic re-assertion. Discord and other apps
    # that also set TopMost can paint over us; this asserts every 600ms.
    try {
        if ("AbsoZOrder" -as [type]) { [AbsoZOrder]::ForceTopmost($form.Handle) }
    } catch {}
    $script:ProgressTopmostTimer = New-Object System.Windows.Forms.Timer
    $script:ProgressTopmostTimer.Interval = 600
    $script:ProgressTopmostTimer.Add_Tick({
        try {
            if ($script:ProgressForm -and -not $script:ProgressForm.IsDisposed) {
                if ("AbsoZOrder" -as [type]) { [AbsoZOrder]::ForceTopmost($script:ProgressForm.Handle) }
            } else {
                $this.Stop(); $this.Dispose()
            }
        } catch { try { $this.Stop(); $this.Dispose() } catch {} }
    })
    $script:ProgressTopmostTimer.Start()

    # Fade-in at monitor refresh rate
    $fadeIn = New-Object System.Windows.Forms.Timer
    $fadeIn.Interval = $script:FrameInterval
    $fadeIn.Add_Tick({
        try {
            if ($script:ProgressForm -and -not $script:ProgressForm.IsDisposed) {
                $op = $script:ProgressForm.Opacity + 0.12
                if ($op -ge 0.98) { $script:ProgressForm.Opacity = 0.98; $this.Stop(); $this.Dispose() }
                else              { $script:ProgressForm.Opacity = $op }
            } else { $this.Stop(); $this.Dispose() }
        } catch { try { $this.Stop(); $this.Dispose() } catch {} }
    })
    $fadeIn.Start()
}

function Update-ProgressOverlay {
    param([string]$StepText)
    if ($script:ProgressForm -and $script:ProgressStepLabel -and -not $script:ProgressForm.IsDisposed) {
        $script:ProgressStepLabel.Text = $StepText
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
    if ($script:ProgressTopmostTimer) {
        try { $script:ProgressTopmostTimer.Stop(); $script:ProgressTopmostTimer.Dispose() } catch {}
        $script:ProgressTopmostTimer = $null
    }
    if ($script:ProgressProfileImageBox) {
        try { $script:ProgressProfileImageBox.Image = $null } catch {}
        $script:ProgressProfileImageBox = $null
    }
    if ($script:ProgressProfileImage) {
        try { $script:ProgressProfileImage.Dispose() } catch {}
        $script:ProgressProfileImage = $null
    }
    if ($script:ProgressDismissButton) {
        try { $script:ProgressDismissButton.Image = $null } catch {}
        $script:ProgressDismissButton = $null
    }
    if ($script:ProgressDismissImage) {
        try { $script:ProgressDismissImage.Dispose() } catch {}
        $script:ProgressDismissImage = $null
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
    $script:ProgressStepLabel    = $null
    $script:ProgressTitleLabel   = $null
    $script:ProgressTrack        = $null
    $script:ProgressFill         = $null
    $script:ProgressElapsedLabel = $null
    $script:ProgressProfileImageBox = $null
    $script:ProgressProfileImage = $null
    $script:ProgressDismissButton = $null
    $script:ProgressDismissImage = $null
}

# ============================================================================
# LEGACY COMPAT
# ============================================================================

function Show-ABSONotification {
    param(
        [string]$Title,
        [string]$Message,
        [ValidateSet("Info","Warning","Error","Success")]
        [string]$Type = "Info",
        [System.Windows.Forms.NotifyIcon]$NotifyIcon,
        [int]$Duration = 4500,
        [string]$MetaText = "",
        [string]$ActionName = "",
        [System.Drawing.Color]$ActionColor = [System.Drawing.Color]::Empty,
        [object[]]$ActionButtons = @()
    )
    if (Get-Command Set-TransientNotificationTooltip -ErrorAction SilentlyContinue) {
        Set-TransientNotificationTooltip -Title $Title -Message $Message
    }
    elseif ($NotifyIcon) {
        $tooltipText = "$Title - $Message"
        if ($tooltipText.Length -gt 63) {
            $tooltipText = $tooltipText.Substring(0, 60) + "..."
        }
        $NotifyIcon.Text = $tooltipText
    }

    $popupToggle = Get-Variable -Name EnableBalloonNotifications -Scope Script -ErrorAction SilentlyContinue
    if ($popupToggle -and -not $script:EnableBalloonNotifications) { return }
    Show-ThemedToast `
        -Title $Title `
        -Message $Message `
        -Type $Type `
        -Duration $Duration `
        -MetaText $MetaText `
        -ActionName $ActionName `
        -ActionColor $ActionColor `
        -ActionButtons @($ActionButtons)
}

# ============================================================================
# STATUS BAR (the disabled menu item that pins to the bottom of the tray menu)
# ============================================================================

function New-StatusBarItem {
    param(
        [string]$LastAction = "Ready",
        [string]$LastActionTime = "",
        [string]$CurrentGame = "",
        [string]$BackupTime = ""
    )
    $dot = " " + [char]0x00B7 + " "
    $parts = @()
    if ($LastAction)  { $parts += $LastAction }
    if ($CurrentGame) { $parts += "Game $CurrentGame" }
    if ($BackupTime)  { $parts += "Backup $BackupTime" }
    $text = "  " + ($parts -join $dot)
    $item = New-Object System.Windows.Forms.ToolStripMenuItem
    $item.Text      = $text
    $item.Enabled   = $false
    $item.BackColor = $script:Penumbra.Ink200
    $item.ForeColor = $script:Penumbra.Fog
    $item.Font      = _Resolve-Font -Families @("Cascadia Mono","Cascadia Code","Consolas") -Size 7.5
    return $item
}
