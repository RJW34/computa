# ABSO-Icons.ps1 - Dynamic icon generation module for A.B.S.O. tray
# Generates tray icons programmatically using GDI+ with gradients and glow effects

# Icon States:
#   Idle            - Computer sprite (default ready state)
#   Active          - Swampert (profile applied)
#   Gaming          - Swampert (game detected and running)
#   Applying        - Pokeball (profile being applied)
#   Warning         - Orange warning indicator
#   Error           - Red error indicator

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;

public class IconHelper {
    [DllImport("user32.dll", CharSet = CharSet.Auto)]
    public static extern bool DestroyIcon(IntPtr handle);
}
"@ -ErrorAction SilentlyContinue

$script:IconSize = 16
$script:AnimationFrame = 0
$script:PreviousIconHandle = [IntPtr]::Zero

function Get-IconFromIcoPath {
    <#
    .SYNOPSIS
    Loads an ICO file and returns a detached icon clone at the specified size.
    #>
    param([string]$Path, [int]$Size = 32)

    if (-not $Path -or -not (Test-Path $Path)) {
        return $null
    }

    $img = $null
    $bmp = $null
    $hIcon = [IntPtr]::Zero
    try {
        $img = [System.Drawing.Image]::FromFile($Path)
        $bmp = New-Object System.Drawing.Bitmap($img, $Size, $Size)
        $hIcon = $bmp.GetHicon()
        $tempIcon = [System.Drawing.Icon]::FromHandle($hIcon)
        $icon = $tempIcon.Clone()
        $tempIcon.Dispose()
        return $icon
    }
    catch {
        return $null
    }
    finally {
        if ($hIcon -ne [IntPtr]::Zero) { [IconHelper]::DestroyIcon($hIcon) | Out-Null }
        if ($bmp) { $bmp.Dispose() }
        if ($img) { $img.Dispose() }
    }
}

function New-ComputerIdleIcon {
    <#
    .SYNOPSIS
    Creates a compact pixel-style "computer" icon for idle state.
    #>
    [int]$size = 16
    $bmp = New-Object System.Drawing.Bitmap($size, $size)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::None
    $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::NearestNeighbor
    $g.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::Half
    $g.Clear([System.Drawing.Color]::Transparent)

    $dark = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::FromArgb(255, 43, 53, 68))
    $bezel = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::FromArgb(255, 76, 92, 112))
    $screen = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::FromArgb(255, 119, 226, 232))
    $scan = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::FromArgb(180, 224, 255, 255))
    $stand = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::FromArgb(255, 155, 171, 194))
    $kbd = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::FromArgb(255, 88, 102, 128))
    $key = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::FromArgb(255, 184, 196, 214))
    $led = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::FromArgb(255, 255, 84, 74))

    # Monitor body + bezel
    $g.FillRectangle($dark, 1, 2, 14, 10)
    $g.FillRectangle($bezel, 2, 3, 12, 8)
    # Screen
    $g.FillRectangle($screen, 3, 4, 10, 6)
    $g.FillRectangle($scan, 4, 5, 8, 1)
    # Status LED
    $g.FillRectangle($led, 12, 10, 1, 1)
    # Stand + keyboard
    $g.FillRectangle($stand, 6, 12, 4, 1)
    $g.FillRectangle($stand, 7, 13, 2, 1)
    $g.FillRectangle($kbd, 4, 14, 8, 2)
    $g.FillRectangle($key, 5, 15, 1, 1)
    $g.FillRectangle($key, 7, 15, 1, 1)
    $g.FillRectangle($key, 9, 15, 1, 1)
    $g.FillRectangle($key, 11, 15, 1, 1)

    $dark.Dispose()
    $bezel.Dispose()
    $screen.Dispose()
    $scan.Dispose()
    $stand.Dispose()
    $kbd.Dispose()
    $key.Dispose()
    $led.Dispose()
    $g.Dispose()

    $hIcon = $bmp.GetHicon()
    $tempIcon = [System.Drawing.Icon]::FromHandle($hIcon)
    $icon = $tempIcon.Clone()
    $tempIcon.Dispose()
    [IconHelper]::DestroyIcon($hIcon) | Out-Null
    $bmp.Dispose()
    return $icon
}

function Get-ApplySuccessIcons {
    <#
    .SYNOPSIS
    Returns icon sequence for "pokeball -> pop -> Swampert".
    #>
    $iconDir = $PSScriptRoot
    $paths = @(
        (Join-Path $iconDir "favicon.ico"),
        (Join-Path $iconDir "icon0260_f00_s0.ico"),
        (Join-Path $iconDir "icon0260_f01_s0.ico"),
        (Join-Path $iconDir "260 Swampert.ico")
    )

    $icons = @()
    foreach ($path in $paths) {
        $icon = Get-IconFromIcoPath -Path $path
        if ($icon) {
            $icons += $icon
        }
    }
    return $icons
}

function New-GlowIcon {
    <#
    .SYNOPSIS
    Creates a 16x16 icon with a glowing circle and optional inner detail.
    .PARAMETER CenterColor
    The bright center color of the glow.
    .PARAMETER GlowColor
    The outer glow color (usually a dimmer version of CenterColor).
    .PARAMETER InnerSymbol
    Optional: "check", "play", "warn", "error", "spin"
    .PARAMETER SpinAngle
    Rotation angle for the spin symbol (0-360).
    #>
    param(
        [System.Drawing.Color]$CenterColor,
        [System.Drawing.Color]$GlowColor,
        [string]$InnerSymbol = "",
        [int]$SpinAngle = 0
    )

    [int]$size = $script:IconSize
    $bmp = New-Object System.Drawing.Bitmap($size, $size)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $g.Clear([System.Drawing.Color]::Transparent)

    # Pre-compute sizes to avoid PowerShell arithmetic issues in method calls
    [int]$sizeM1 = $size - 1
    [int]$sizeM5 = $size - 5
    [int]$sizeM7 = $size - 7
    [int]$sizeM9 = $size - 9

    # Outer glow (larger, semi-transparent)
    $glowBrush = New-Object System.Drawing.SolidBrush(
        [System.Drawing.Color]::FromArgb(80, $GlowColor.R, $GlowColor.G, $GlowColor.B)
    )
    $g.FillEllipse($glowBrush, 0, 0, $sizeM1, $sizeM1)
    $glowBrush.Dispose()

    # Mid ring
    $midBrush = New-Object System.Drawing.SolidBrush(
        [System.Drawing.Color]::FromArgb(140, $GlowColor.R, $GlowColor.G, $GlowColor.B)
    )
    $g.FillEllipse($midBrush, 2, 2, $sizeM5, $sizeM5)
    $midBrush.Dispose()

    # Inner bright circle with gradient
    $innerRect = New-Object System.Drawing.Rectangle(3, 3, $sizeM7, $sizeM7)
    $innerBrush = $null
    try {
        $innerBrush = New-Object System.Drawing.Drawing2D.LinearGradientBrush(
            $innerRect,
            [System.Drawing.Color]::FromArgb(255, [Math]::Min(255, $CenterColor.R + 40), [Math]::Min(255, $CenterColor.G + 40), [Math]::Min(255, $CenterColor.B + 40)),
            $CenterColor,
            [System.Drawing.Drawing2D.LinearGradientMode]::ForwardDiagonal
        )
    }
    catch {
        $innerBrush = New-Object System.Drawing.SolidBrush($CenterColor)
    }
    try {
        $g.FillEllipse($innerBrush, $innerRect)
    }
    finally {
        if ($innerBrush) { $innerBrush.Dispose() }
    }

    # Inner symbol
    switch ($InnerSymbol) {
        "check" {
            $pen = New-Object System.Drawing.Pen([System.Drawing.Color]::White, 1.8)
            $pen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
            $pen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
            $cx = $size / 2
            $cy = $size / 2
            $g.DrawLine($pen, ($cx - 2), $cy, ($cx - 0.5), ($cy + 2))
            $g.DrawLine($pen, ($cx - 0.5), ($cy + 2), ($cx + 2.5), ($cy - 1.5))
            $pen.Dispose()
        }
        "play" {
            $brush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::White)
            $points = @(
                (New-Object System.Drawing.PointF(6, 4)),
                (New-Object System.Drawing.PointF(12, 8)),
                (New-Object System.Drawing.PointF(6, 12))
            )
            $g.FillPolygon($brush, $points)
            $brush.Dispose()
        }
        "warn" {
            $brush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::White)
            $font = New-Object System.Drawing.Font("Segoe UI", 7, [System.Drawing.FontStyle]::Bold)
            $sf = New-Object System.Drawing.StringFormat
            $sf.Alignment = [System.Drawing.StringAlignment]::Center
            $sf.LineAlignment = [System.Drawing.StringAlignment]::Center
            $rect = New-Object System.Drawing.RectangleF(0, -1, $size, $size)
            $g.DrawString("!", $font, $brush, $rect, $sf)
            $font.Dispose()
            $brush.Dispose()
            $sf.Dispose()
        }
        "error" {
            $pen = New-Object System.Drawing.Pen([System.Drawing.Color]::White, 1.8)
            $pen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
            $pen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
            $cx = $size / 2
            $cy = $size / 2
            $g.DrawLine($pen, ($cx - 2), ($cy - 2), ($cx + 2), ($cy + 2))
            $g.DrawLine($pen, ($cx + 2), ($cy - 2), ($cx - 2), ($cy + 2))
            $pen.Dispose()
        }
        "spin" {
            # Animated arc spinner
            $pen = New-Object System.Drawing.Pen([System.Drawing.Color]::White, 1.5)
            $pen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
            $pen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
            $arcRect = New-Object System.Drawing.Rectangle(4, 4, $sizeM9, $sizeM9)
            $g.DrawArc($pen, $arcRect, $SpinAngle, 240)
            $pen.Dispose()
        }
    }

    # Highlight dot (top-left specular)
    $highlightBrush = New-Object System.Drawing.SolidBrush(
        [System.Drawing.Color]::FromArgb(90, 255, 255, 255)
    )
    $g.FillEllipse($highlightBrush, 4, 3, 4, 3)
    $highlightBrush.Dispose()

    $g.Dispose()

    $hIcon = $bmp.GetHicon()
    $tempIcon = [System.Drawing.Icon]::FromHandle($hIcon)
    $icon = $tempIcon.Clone()
    $tempIcon.Dispose()
    [IconHelper]::DestroyIcon($hIcon) | Out-Null
    $bmp.Dispose()
    return $icon
}

# Pre-defined icon state colors
$script:IconColors = @{
    Idle = @{
        Center = [System.Drawing.Color]::FromArgb(255, 220, 180, 70)
        Glow   = [System.Drawing.Color]::FromArgb(255, 180, 140, 40)
    }
    Active = @{
        Center = [System.Drawing.Color]::FromArgb(255, 90, 200, 120)
        Glow   = [System.Drawing.Color]::FromArgb(255, 50, 160, 80)
    }
    Gaming = @{
        Center = [System.Drawing.Color]::FromArgb(255, 80, 160, 230)
        Glow   = [System.Drawing.Color]::FromArgb(255, 50, 120, 190)
    }
    Applying = @{
        Center = [System.Drawing.Color]::FromArgb(255, 140, 120, 220)
        Glow   = [System.Drawing.Color]::FromArgb(255, 100, 80, 180)
    }
    Warning = @{
        Center = [System.Drawing.Color]::FromArgb(255, 240, 180, 60)
        Glow   = [System.Drawing.Color]::FromArgb(255, 200, 140, 30)
    }
    Error = @{
        Center = [System.Drawing.Color]::FromArgb(255, 220, 70, 70)
        Glow   = [System.Drawing.Color]::FromArgb(255, 180, 40, 40)
    }
}

function New-StateIcon {
    <#
    .SYNOPSIS
    Creates an icon for a named state.
    .PARAMETER State
    One of: Idle, Active, Gaming, Applying, Warning, Error
    #>
    param(
        [ValidateSet("Idle", "Active", "Gaming", "Applying", "Warning", "Error")]
        [string]$State = "Idle"
    )

    $iconDir = $PSScriptRoot

    # Primary themed icon mapping first
    if ($State -eq "Idle") {
        $idlePath = Join-Path $iconDir "pokemon_pc_idle.ico"
        $idleIcon = Get-IconFromIcoPath -Path $idlePath
        if ($idleIcon) {
            return $idleIcon
        }
        return New-ComputerIdleIcon
    }

    $themedPath = $null
    if ($State -eq "Applying") {
        $themedPath = Join-Path $iconDir "favicon.ico"
    }
    elseif ($State -eq "Active" -or $State -eq "Gaming") {
        $themedPath = Join-Path $iconDir "260 Swampert.ico"
    }

    if ($themedPath) {
        $themedIcon = Get-IconFromIcoPath -Path $themedPath
        if ($themedIcon) {
            return $themedIcon
        }
    }

    $colors = $script:IconColors[$State]
    $symbol = switch ($State) {
        "Idle"     { "" }
        "Active"   { "check" }
        "Gaming"   { "play" }
        "Applying" { "spin" }
        "Warning"  { "warn" }
        "Error"    { "error" }
    }

    return New-GlowIcon -CenterColor $colors.Center -GlowColor $colors.Glow -InnerSymbol $symbol -SpinAngle 0
}

function New-CategoryIcon {
    <#
    .SYNOPSIS
    Creates a small 16x16 icon for a profile category.
    Delegates to New-CategoryBitmap and converts the bitmap to an icon.
    .PARAMETER Category
    One of: Desktop, Fighting, Shooters, RPGs, Other (legacy category names are accepted)
    #>
    param([string]$Category)

    $bmp = New-CategoryBitmap -Category $Category -Color ([System.Drawing.Color]::White)
    $hIcon = $bmp.GetHicon()
    $tempIcon = [System.Drawing.Icon]::FromHandle($hIcon)
    $icon = $tempIcon.Clone()
    $tempIcon.Dispose()
    [IconHelper]::DestroyIcon($hIcon) | Out-Null
    $bmp.Dispose()
    return $icon
}

function New-CategoryBitmap {
    <#
    .SYNOPSIS
    Creates a 16x16 bitmap for a profile category using filled shapes with depth.
    Uses the three-layer depth system: shadow/glow, main fill with gradient, specular highlight.
    .PARAMETER Category
    One of: Desktop, Fighting, Shooters, RPGs, Other (legacy category names are accepted)
    .PARAMETER Color
    The category color for fills and strokes.
    #>
    param(
        [string]$Category,
        [System.Drawing.Color]$Color = [System.Drawing.Color]::White
    )

    $iconCategory = switch ($Category) {
        "Desktop" { "Productivity" }
        "Shooters" { "Shooter" }
        "RPGs" { "ARPG" }
        "Other Games" { "Other" }
        default { $Category }
    }

    $bmp = New-Object System.Drawing.Bitmap(16, 16)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $g.Clear([System.Drawing.Color]::Transparent)

    # Three-layer depth system shared resources
    $glowBrush = New-Object System.Drawing.SolidBrush(
        [System.Drawing.Color]::FromArgb(40, $Color.R, $Color.G, $Color.B)
    )
    $highlightBrush = New-Object System.Drawing.SolidBrush(
        [System.Drawing.Color]::FromArgb(70, 255, 255, 255)
    )
    $lighter = [System.Drawing.Color]::FromArgb(255,
        [Math]::Min(255, [int]$Color.R + 50),
        [Math]::Min(255, [int]$Color.G + 50),
        [Math]::Min(255, [int]$Color.B + 50)
    )
    $darker = [System.Drawing.Color]::FromArgb(255,
        [Math]::Max(0, [int]$Color.R - 60),
        [Math]::Max(0, [int]$Color.G - 60),
        [Math]::Max(0, [int]$Color.B - 60)
    )

    switch ($iconCategory) {
        "Fighting" {
            # Crossed blades — thick strokes with guards and pommels
            # Layer 1: Glow behind crossing point
            $g.FillEllipse($glowBrush, 4, 4, 8, 8)

            # Layer 2: Thick crossed blade strokes
            $bladePen = New-Object System.Drawing.Pen($Color, 2.5)
            $bladePen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
            $bladePen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
            $g.DrawLine($bladePen, 3, 13, 13, 2)
            $g.DrawLine($bladePen, 13, 13, 3, 2)
            $bladePen.Dispose()

            # Guard cross-bars (darker)
            $guardPen = New-Object System.Drawing.Pen($darker, 1.8)
            $guardPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
            $guardPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
            $g.DrawLine($guardPen, 2, 10, 5, 10)
            $g.DrawLine($guardPen, 11, 10, 14, 10)
            $guardPen.Dispose()

            # Pommel dots
            $pommelBrush = New-Object System.Drawing.SolidBrush($lighter)
            $g.FillEllipse($pommelBrush, [float]1.5, [float]12, [float]2.5, [float]2.5)
            $g.FillEllipse($pommelBrush, [float]12, [float]12, [float]2.5, [float]2.5)
            $pommelBrush.Dispose()

            # Layer 3: Specular highlight
            $g.FillEllipse($highlightBrush, 5, 3, 4, 3)
        }
        "ARPG" {
            # Filled gradient shield with diamond emblem
            $points = [System.Drawing.PointF[]]@(
                (New-Object System.Drawing.PointF(8, 2)),
                (New-Object System.Drawing.PointF(13, 4)),
                (New-Object System.Drawing.PointF(12, 10)),
                (New-Object System.Drawing.PointF(8, 14)),
                (New-Object System.Drawing.PointF(4, 10)),
                (New-Object System.Drawing.PointF(3, 4))
            )

            # Layer 1: Glow behind shield
            $g.FillEllipse($glowBrush, 2, 1, 12, 14)

            # Layer 2: Filled gradient shield
            $shieldRect = New-Object System.Drawing.Rectangle(3, 2, 10, 12)
            $gradBrush = $null
            try {
                $gradBrush = New-Object System.Drawing.Drawing2D.LinearGradientBrush(
                    $shieldRect, $lighter, $Color,
                    [System.Drawing.Drawing2D.LinearGradientMode]::Vertical
                )
            } catch {
                $gradBrush = New-Object System.Drawing.SolidBrush($Color)
            }
            $g.FillPolygon($gradBrush, $points)
            $gradBrush.Dispose()

            # Darker border
            $borderPen = New-Object System.Drawing.Pen($darker, 1.0)
            $g.DrawPolygon($borderPen, $points)
            $borderPen.Dispose()

            # Center diamond emblem
            $diamondPoints = [System.Drawing.PointF[]]@(
                (New-Object System.Drawing.PointF(8, 5)),
                (New-Object System.Drawing.PointF(10, 8)),
                (New-Object System.Drawing.PointF(8, 11)),
                (New-Object System.Drawing.PointF(6, 8))
            )
            $diamondBrush = New-Object System.Drawing.SolidBrush($lighter)
            $g.FillPolygon($diamondBrush, $diamondPoints)
            $diamondBrush.Dispose()

            # Layer 3: Specular highlight
            $g.FillEllipse($highlightBrush, 5, 3, 5, 3)
        }
        "Shooter" {
            # Filled crosshair reticle with center dot
            # Layer 1: Subtle circle fill
            $g.FillEllipse($glowBrush, 3, 3, 10, 10)
            $innerFill = New-Object System.Drawing.SolidBrush(
                [System.Drawing.Color]::FromArgb(25, $Color.R, $Color.G, $Color.B)
            )
            $g.FillEllipse($innerFill, 4, 4, 8, 8)
            $innerFill.Dispose()

            # Layer 2: Thicker reticle with center gap
            $reticlePen = New-Object System.Drawing.Pen($Color, 1.6)
            $reticlePen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
            $reticlePen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
            $g.DrawEllipse($reticlePen, 3, 3, 10, 10)
            $g.DrawLine($reticlePen, 8, 1, 8, 5)
            $g.DrawLine($reticlePen, 8, 11, 8, 15)
            $g.DrawLine($reticlePen, 1, 8, 5, 8)
            $g.DrawLine($reticlePen, 11, 8, 15, 8)
            $reticlePen.Dispose()

            # Filled center dot
            $dotBrush = New-Object System.Drawing.SolidBrush($lighter)
            $g.FillEllipse($dotBrush, [float]6.5, [float]6.5, [float]3, [float]3)
            $dotBrush.Dispose()

            # Layer 3: Specular highlight
            $g.FillEllipse($highlightBrush, 4, 3, 4, 3)
        }
        "Productivity" {
            # Filled monitor with gradient screen, scanline, and stand
            # Layer 1: Glow behind monitor
            $g.FillEllipse($glowBrush, 1, 1, 14, 12)

            # Layer 2: Filled dark bezel
            $bezelBrush = New-Object System.Drawing.SolidBrush($darker)
            $g.FillRectangle($bezelBrush, 2, 2, 12, 8)
            $bezelBrush.Dispose()

            # Gradient screen area
            $screenRect = New-Object System.Drawing.Rectangle(3, 3, 10, 6)
            $screenBrush = $null
            try {
                $screenBrush = New-Object System.Drawing.Drawing2D.LinearGradientBrush(
                    $screenRect, $lighter, $Color,
                    [System.Drawing.Drawing2D.LinearGradientMode]::Vertical
                )
            } catch {
                $screenBrush = New-Object System.Drawing.SolidBrush($Color)
            }
            $g.FillRectangle($screenBrush, $screenRect)
            $screenBrush.Dispose()

            # Scanline highlight
            $scanBrush = New-Object System.Drawing.SolidBrush(
                [System.Drawing.Color]::FromArgb(50, 255, 255, 255)
            )
            $g.FillRectangle($scanBrush, 4, 4, 8, 1)
            $scanBrush.Dispose()

            # Filled stand and base
            $standBrush = New-Object System.Drawing.SolidBrush($Color)
            $g.FillRectangle($standBrush, 7, 10, 2, 2)
            $g.FillRectangle($standBrush, 5, 12, 6, 2)
            $standBrush.Dispose()

            # Layer 3: Specular highlight
            $g.FillEllipse($highlightBrush, 4, 3, 5, 2)
        }
        "Streaming" {
            # Broadcast arcs with filled antenna base
            # Layer 1: Background glow
            $g.FillEllipse($glowBrush, 2, 2, 12, 12)

            # Layer 2: Thicker broadcast arcs
            $arcPen = New-Object System.Drawing.Pen($Color, 1.8)
            $arcPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
            $arcPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
            $g.DrawArc($arcPen, 1, 3, 14, 14, 220, 100)
            $g.DrawArc($arcPen, 3, 5, 10, 10, 220, 100)
            $g.DrawArc($arcPen, 5, 7, 6, 6, 220, 100)
            $arcPen.Dispose()

            # Filled triangular antenna base
            $antennaPoints = @(
                (New-Object System.Drawing.PointF(5.5, 14)),
                (New-Object System.Drawing.PointF(10.5, 14)),
                (New-Object System.Drawing.PointF(8, 10))
            )
            $antennaBrush = New-Object System.Drawing.SolidBrush($Color)
            $g.FillPolygon($antennaBrush, $antennaPoints)
            $antennaBrush.Dispose()

            # Bright emitter dot
            $tipBrush = New-Object System.Drawing.SolidBrush($lighter)
            $g.FillEllipse($tipBrush, [float]6.5, [float]9, [float]3, [float]3)
            $tipBrush.Dispose()

            # Layer 3: Specular highlight
            $g.FillEllipse($highlightBrush, 4, 4, 4, 3)
        }
        default {
            # Other: Filled 8-pointed star with gradient and center circle
            # Layer 1: Glow behind
            $g.FillEllipse($glowBrush, 1, 1, 14, 14)

            # Layer 2: 8-pointed star polygon
            [float]$cx = 8.0
            [float]$cy = 8.0
            [float]$outerR = 6.5
            [float]$innerR = 3.0
            $starPoints = @()
            for ($i = 0; $i -lt 16; $i++) {
                [float]$angle = ($i * 22.5 - 90) * [Math]::PI / 180
                [float]$r = if ($i % 2 -eq 0) { $outerR } else { $innerR }
                $starPoints += New-Object System.Drawing.PointF(
                    ($cx + $r * [Math]::Cos($angle)),
                    ($cy + $r * [Math]::Sin($angle))
                )
            }

            $starRect = New-Object System.Drawing.Rectangle(1, 1, 14, 14)
            $starBrush = $null
            try {
                $starBrush = New-Object System.Drawing.Drawing2D.LinearGradientBrush(
                    $starRect, $lighter, $Color,
                    [System.Drawing.Drawing2D.LinearGradientMode]::ForwardDiagonal
                )
            } catch {
                $starBrush = New-Object System.Drawing.SolidBrush($Color)
            }
            $g.FillPolygon($starBrush, $starPoints)
            $starBrush.Dispose()

            # Bright center circle
            $centerBrush = New-Object System.Drawing.SolidBrush($lighter)
            $g.FillEllipse($centerBrush, 6, 6, 4, 4)
            $centerBrush.Dispose()

            # Layer 3: Specular highlight
            $g.FillEllipse($highlightBrush, 4, 3, 5, 3)
        }
    }

    $glowBrush.Dispose()
    $highlightBrush.Dispose()
    $g.Dispose()
    return $bmp
}

function Resolve-GameVisualIdentityGroup {
    <#
    .SYNOPSIS
    Normalizes profile ids, catalog game groups, and display group labels to a
    known game visual identity key when possible.
    #>
    param([AllowNull()][string]$GameGroup)

    if ([string]::IsNullOrWhiteSpace($GameGroup)) { return "" }

    $normalized = "$GameGroup".Trim().ToLowerInvariant()
    $normalized = $normalized -replace '\s*/\s*', '-'
    $normalized = $normalized -replace '[\s_]+', '-'
    $normalized = $normalized -replace '[()]', ''
    $normalized = $normalized -replace '[^a-z0-9-]+', '-'
    $normalized = $normalized -replace '-+', '-'
    $normalized = $normalized.Trim('-')

    $knownGameGroups = @(
        "slippi-melee", "rivals2", "overwatch2", "fortnite", "marvel-rivals",
        "deadlock", "call-of-duty", "diablo4", "ryujinx-ssbu", "pokemon-auto-chess",
        "pacdeluxe", "productivity", "valorant", "apex-legends", "counter-strike-2",
        "rocket-league", "minecraft", "league-of-legends", "destiny-2",
        "elden-ring", "halo-infinite", "cyberpunk-2077", "helldivers-2"
    )
    $aliases = @{
        "super-smash-bros-melee-slippi" = "slippi-melee"
        "melee-slippi" = "slippi-melee"
        "slippi-launcher" = "slippi-melee"
        "slippi-dolphin" = "slippi-melee"
        "slippi-dolphin-exe" = "slippi-melee"
        "dolphin" = "slippi-melee"
        "dolphin-exe" = "slippi-melee"
        "rivals-2" = "rivals2"
        "rivals-of-aether-2" = "rivals2"
        "rivalsofaether2" = "rivals2"
        "rivalsofaether2-exe" = "rivals2"
        "rivalsofaether2-win64-shipping" = "rivals2"
        "rivalsofaether2-win64-shipping-exe" = "rivals2"
        "overwatch-2" = "overwatch2"
        "overwatch" = "overwatch2"
        "overwatch-exe" = "overwatch2"
        "ow2" = "overwatch2"
        "call-of-duty" = "call-of-duty"
        "callofduty" = "call-of-duty"
        "cod" = "call-of-duty"
        "cod-exe" = "call-of-duty"
        "cod-bo6" = "call-of-duty"
        "cod-bo7" = "call-of-duty"
        "bo6" = "call-of-duty"
        "bo7" = "call-of-duty"
        "blackops6" = "call-of-duty"
        "blackops7" = "call-of-duty"
        "black-ops-6" = "call-of-duty"
        "black-ops-7" = "call-of-duty"
        "call-of-duty-black-ops-6" = "call-of-duty"
        "call-of-duty-black-ops-7" = "call-of-duty"
        "warzone" = "call-of-duty"
        "call-of-duty-warzone" = "call-of-duty"
        "mw2" = "call-of-duty"
        "mw3" = "call-of-duty"
        "modernwarfare2" = "call-of-duty"
        "modernwarfare3" = "call-of-duty"
        "modernwarfare" = "call-of-duty"
        "modernwarfare-exe" = "call-of-duty"
        "modern-warfare" = "call-of-duty"
        "modern-warfare-exe" = "call-of-duty"
        "call-of-duty-modern-warfare" = "call-of-duty"
        "modern-warfare-ii" = "call-of-duty"
        "modern-warfare-iii" = "call-of-duty"
        "call-of-duty-modern-warfare-ii" = "call-of-duty"
        "call-of-duty-modern-warfare-iii" = "call-of-duty"
        "diablo-4" = "diablo4"
        "diablo-iv" = "diablo4"
        "diablo-iv-exe" = "diablo4"
        "diabloiv" = "diablo4"
        "marvelrivals" = "marvel-rivals"
        "marvel-exe" = "marvel-rivals"
        "marvel-win64-shipping" = "marvel-rivals"
        "marvel-win64-shipping-exe" = "marvel-rivals"
        "fortniteclient-win64-shipping" = "fortnite"
        "fortniteclient-win64-shipping-exe" = "fortnite"
        "fortniteclient-win64-shipping-eac" = "fortnite"
        "fortniteclient-win64-shipping-eac-exe" = "fortnite"
        "fortniteclient-win64-shipping-be" = "fortnite"
        "fortniteclient-win64-shipping-be-exe" = "fortnite"
        "fortniteclient-win64-shipping-eac-eos" = "fortnite"
        "fortniteclient-win64-shipping-eac-eos-exe" = "fortnite"
        "ssbu-hewdraw-remix-ryujinx" = "ryujinx-ssbu"
        "super-smash-bros-ultimate-ryujinx" = "ryujinx-ssbu"
        "ryujinx" = "ryujinx-ssbu"
        "ryujinx-exe" = "ryujinx-ssbu"
        "pac-deluxe" = "pacdeluxe"
        "pacdeluxe-pokemon-auto-chess" = "pacdeluxe"
        "pac-deluxe-pokemon-auto-chess" = "pacdeluxe"
        "valorant-win64-shipping" = "valorant"
        "valorant-win64-shipping-exe" = "valorant"
        "valorant-exe" = "valorant"
        "apex" = "apex-legends"
        "r5apex" = "apex-legends"
        "r5apex-exe" = "apex-legends"
        "counter-strike" = "counter-strike-2"
        "counter-strike-2" = "counter-strike-2"
        "cs2" = "counter-strike-2"
        "cs2-exe" = "counter-strike-2"
        "rocketleague" = "rocket-league"
        "rocketleague-exe" = "rocket-league"
        "rocketleague-win64-shipping" = "rocket-league"
        "rocketleague-win64-shipping-exe" = "rocket-league"
        "minecraftlauncher" = "minecraft"
        "minecraftlauncher-exe" = "minecraft"
        "leagueoflegends" = "league-of-legends"
        "league-of-legends-exe" = "league-of-legends"
        "leagueclient" = "league-of-legends"
        "leagueclient-exe" = "league-of-legends"
        "destiny2" = "destiny-2"
        "destiny-2-exe" = "destiny-2"
        "destiny2-exe" = "destiny-2"
        "eldenring" = "elden-ring"
        "elden-ring-exe" = "elden-ring"
        "eldenring-exe" = "elden-ring"
        "halo" = "halo-infinite"
        "halo-infinite-exe" = "halo-infinite"
        "haloinfinite" = "halo-infinite"
        "haloinfinite-exe" = "halo-infinite"
        "cyberpunk" = "cyberpunk-2077"
        "cyberpunk2077" = "cyberpunk-2077"
        "cyberpunk-2077-exe" = "cyberpunk-2077"
        "cyberpunk2077-exe" = "cyberpunk-2077"
        "helldivers2" = "helldivers-2"
        "helldivers-2-exe" = "helldivers-2"
        "helldivers2-exe" = "helldivers-2"
        "desktop-productivity" = "productivity"
        "desktop" = "productivity"
    }

    if ($aliases.ContainsKey($normalized)) { return $aliases[$normalized] }
    if ($knownGameGroups.Contains($normalized)) { return $normalized }

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
        if ($normalized.EndsWith($suffix)) {
            $candidate = $normalized.Substring(0, $normalized.Length - $suffix.Length)
            if ($aliases.ContainsKey($candidate)) { return $aliases[$candidate] }
            if ($knownGameGroups.Contains($candidate)) { return $candidate }
        }
    }

    return $normalized
}

function Get-GameVisualIdentity {
    <#
    .SYNOPSIS
    Returns tray-safe visual identity metadata for known game groups.

    .DESCRIPTION
    These are compact, stylized in-tray marks rather than bundled trademark
    assets. The palette lets every shipped game read as its own title across
    menu rows, quick-panel cards, progress overlays, and toasts.
    #>
    param(
        [string]$GameGroup,
        [System.Drawing.Color]$FallbackColor = [System.Drawing.Color]::White
    )

    $resolvedGameGroup = Resolve-GameVisualIdentityGroup -GameGroup $GameGroup
    $fallbackSecondary = [System.Drawing.Color]::FromArgb(255,
        [Math]::Min(255, [int]$FallbackColor.R + 45),
        [Math]::Min(255, [int]$FallbackColor.G + 45),
        [Math]::Min(255, [int]$FallbackColor.B + 45)
    )
    $fallbackShadow = [System.Drawing.Color]::FromArgb(255,
        [Math]::Max(0, [int]$FallbackColor.R - 70),
        [Math]::Max(0, [int]$FallbackColor.G - 70),
        [Math]::Max(0, [int]$FallbackColor.B - 70)
    )

    $identity = switch ("$resolvedGameGroup") {
        "slippi-melee" {
            @{
                Name = "Melee"; Primary = [System.Drawing.Color]::FromArgb(255, 250, 74, 85)
                Secondary = [System.Drawing.Color]::FromArgb(255, 255, 214, 98)
                Shadow = [System.Drawing.Color]::FromArgb(255, 67, 31, 45)
            }
        }
        "rivals2" {
            @{
                Name = "Rivals"; Primary = [System.Drawing.Color]::FromArgb(255, 255, 126, 54)
                Secondary = [System.Drawing.Color]::FromArgb(255, 255, 218, 86)
                Shadow = [System.Drawing.Color]::FromArgb(255, 78, 31, 24)
            }
        }
        "overwatch2" {
            @{
                Name = "Overwatch"; Primary = [System.Drawing.Color]::FromArgb(255, 248, 154, 37)
                Secondary = [System.Drawing.Color]::FromArgb(255, 235, 239, 245)
                Shadow = [System.Drawing.Color]::FromArgb(255, 47, 59, 80)
            }
        }
        "fortnite" {
            @{
                Name = "Fortnite"; Primary = [System.Drawing.Color]::FromArgb(255, 164, 95, 255)
                Secondary = [System.Drawing.Color]::FromArgb(255, 89, 218, 255)
                Shadow = [System.Drawing.Color]::FromArgb(255, 52, 34, 91)
            }
        }
        "marvel-rivals" {
            @{
                Name = "Marvel Rivals"; Primary = [System.Drawing.Color]::FromArgb(255, 255, 196, 66)
                Secondary = [System.Drawing.Color]::FromArgb(255, 255, 77, 77)
                Shadow = [System.Drawing.Color]::FromArgb(255, 82, 28, 31)
            }
        }
        "deadlock" {
            @{
                Name = "Deadlock"; Primary = [System.Drawing.Color]::FromArgb(255, 170, 139, 91)
                Secondary = [System.Drawing.Color]::FromArgb(255, 104, 219, 172)
                Shadow = [System.Drawing.Color]::FromArgb(255, 38, 45, 48)
            }
        }
        "call-of-duty" {
            @{
                Name = "Call of Duty"; Primary = [System.Drawing.Color]::FromArgb(255, 128, 176, 90)
                Secondary = [System.Drawing.Color]::FromArgb(255, 224, 238, 196)
                Shadow = [System.Drawing.Color]::FromArgb(255, 28, 38, 31)
            }
        }
        "diablo4" {
            @{
                Name = "Diablo IV"; Primary = [System.Drawing.Color]::FromArgb(255, 210, 45, 48)
                Secondary = [System.Drawing.Color]::FromArgb(255, 255, 150, 92)
                Shadow = [System.Drawing.Color]::FromArgb(255, 62, 13, 23)
            }
        }
        "ryujinx-ssbu" {
            @{
                Name = "SSBU"; Primary = [System.Drawing.Color]::FromArgb(255, 55, 169, 255)
                Secondary = [System.Drawing.Color]::FromArgb(255, 255, 77, 88)
                Shadow = [System.Drawing.Color]::FromArgb(255, 29, 43, 71)
            }
        }
        "pokemon-auto-chess" {
            @{
                Name = "Pokemon Auto Chess"; Primary = [System.Drawing.Color]::FromArgb(255, 231, 66, 64)
                Secondary = [System.Drawing.Color]::FromArgb(255, 249, 249, 242)
                Shadow = [System.Drawing.Color]::FromArgb(255, 34, 38, 50)
            }
        }
        "pacdeluxe" {
            @{
                Name = "PAC Deluxe"; Primary = [System.Drawing.Color]::FromArgb(255, 255, 214, 49)
                Secondary = [System.Drawing.Color]::FromArgb(255, 88, 215, 255)
                Shadow = [System.Drawing.Color]::FromArgb(255, 49, 33, 18)
            }
        }
        "productivity" {
            @{
                Name = "Productivity"; Primary = [System.Drawing.Color]::FromArgb(255, 0, 245, 212)
                Secondary = [System.Drawing.Color]::FromArgb(255, 150, 222, 255)
                Shadow = [System.Drawing.Color]::FromArgb(255, 20, 43, 56)
            }
        }
        "valorant" {
            @{
                Name = "Valorant"; Primary = [System.Drawing.Color]::FromArgb(255, 255, 70, 85)
                Secondary = [System.Drawing.Color]::FromArgb(255, 235, 239, 234)
                Shadow = [System.Drawing.Color]::FromArgb(255, 50, 24, 33)
            }
        }
        "apex-legends" {
            @{
                Name = "Apex Legends"; Primary = [System.Drawing.Color]::FromArgb(255, 219, 52, 48)
                Secondary = [System.Drawing.Color]::FromArgb(255, 244, 190, 102)
                Shadow = [System.Drawing.Color]::FromArgb(255, 62, 30, 24)
            }
        }
        "counter-strike-2" {
            @{
                Name = "Counter-Strike 2"; Primary = [System.Drawing.Color]::FromArgb(255, 245, 159, 52)
                Secondary = [System.Drawing.Color]::FromArgb(255, 120, 220, 208)
                Shadow = [System.Drawing.Color]::FromArgb(255, 42, 43, 38)
            }
        }
        "rocket-league" {
            @{
                Name = "Rocket League"; Primary = [System.Drawing.Color]::FromArgb(255, 63, 154, 255)
                Secondary = [System.Drawing.Color]::FromArgb(255, 255, 157, 54)
                Shadow = [System.Drawing.Color]::FromArgb(255, 23, 46, 88)
            }
        }
        "minecraft" {
            @{
                Name = "Minecraft"; Primary = [System.Drawing.Color]::FromArgb(255, 95, 171, 75)
                Secondary = [System.Drawing.Color]::FromArgb(255, 146, 93, 58)
                Shadow = [System.Drawing.Color]::FromArgb(255, 48, 69, 38)
            }
        }
        "league-of-legends" {
            @{
                Name = "League of Legends"; Primary = [System.Drawing.Color]::FromArgb(255, 202, 163, 80)
                Secondary = [System.Drawing.Color]::FromArgb(255, 79, 193, 219)
                Shadow = [System.Drawing.Color]::FromArgb(255, 26, 39, 64)
            }
        }
        "destiny-2" {
            @{
                Name = "Destiny 2"; Primary = [System.Drawing.Color]::FromArgb(255, 235, 239, 245)
                Secondary = [System.Drawing.Color]::FromArgb(255, 103, 180, 255)
                Shadow = [System.Drawing.Color]::FromArgb(255, 42, 53, 72)
            }
        }
        "elden-ring" {
            @{
                Name = "Elden Ring"; Primary = [System.Drawing.Color]::FromArgb(255, 217, 174, 86)
                Secondary = [System.Drawing.Color]::FromArgb(255, 148, 216, 132)
                Shadow = [System.Drawing.Color]::FromArgb(255, 44, 39, 25)
            }
        }
        "halo-infinite" {
            @{
                Name = "Halo Infinite"; Primary = [System.Drawing.Color]::FromArgb(255, 87, 148, 116)
                Secondary = [System.Drawing.Color]::FromArgb(255, 255, 201, 84)
                Shadow = [System.Drawing.Color]::FromArgb(255, 23, 48, 42)
            }
        }
        "cyberpunk-2077" {
            @{
                Name = "Cyberpunk 2077"; Primary = [System.Drawing.Color]::FromArgb(255, 246, 232, 43)
                Secondary = [System.Drawing.Color]::FromArgb(255, 0, 233, 255)
                Shadow = [System.Drawing.Color]::FromArgb(255, 65, 26, 74)
            }
        }
        "helldivers-2" {
            @{
                Name = "Helldivers 2"; Primary = [System.Drawing.Color]::FromArgb(255, 255, 205, 64)
                Secondary = [System.Drawing.Color]::FromArgb(255, 235, 239, 245)
                Shadow = [System.Drawing.Color]::FromArgb(255, 46, 50, 57)
            }
        }
        default { $null }
    }

    if (-not $identity) {
        return @{
            Name = "$GameGroup"; Primary = $FallbackColor
            Secondary = $fallbackSecondary; Shadow = $fallbackShadow
            Key = $resolvedGameGroup
            IsKnown = $false
        }
    }

    $identity["Key"] = $resolvedGameGroup
    $identity["IsKnown"] = $true
    return $identity
}

function Get-GameAccentColor {
    <#
    .SYNOPSIS
    Gets the brand/stylized accent color for a game group.

    Unknown non-empty game groups use the same deterministic fallback palette
    as New-StylizedGameFallbackBitmap so their menu rows, toasts, progress
    overlays, and quick-panel cards match the generated mark.
    #>
    param(
        [string]$GameGroup,
        [System.Drawing.Color]$FallbackColor = [System.Drawing.Color]::White
    )

    $identity = Get-GameVisualIdentity -GameGroup $GameGroup -FallbackColor $FallbackColor
    if ($identity -and $identity.IsKnown) { return $identity.Primary }
    if (-not [string]::IsNullOrWhiteSpace($GameGroup)) {
        return Get-GameFallbackColor -GameGroup $GameGroup -FallbackColor $FallbackColor
    }
    return $FallbackColor
}

function Get-GameFallbackInitials {
    param([string]$GameGroup)

    $raw = if ([string]::IsNullOrWhiteSpace($GameGroup)) { "" } else { "$GameGroup" }
    $clean = (($raw -replace '[_\-.]+', ' ') -replace '[^A-Za-z0-9 ]', ' ').Trim()
    if ([string]::IsNullOrWhiteSpace($clean)) { return "?" }

    $parts = @($clean -split '\s+' | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    if ($parts.Count -ge 2) {
        return "$($parts[0].Substring(0, 1))$($parts[1].Substring(0, 1))".ToUpperInvariant()
    }

    $single = "$($parts[0])"
    if ($single.Length -ge 2) {
        return $single.Substring(0, 2).ToUpperInvariant()
    }
    return $single.Substring(0, 1).ToUpperInvariant()
}

function Get-GameFallbackHash {
    param([string]$GameGroup)

    [long]$hash = 17
    foreach ($ch in "$GameGroup".ToCharArray()) {
        $hash = (($hash * 31) + [int][char]$ch) % 2147483647
    }
    return [int]$hash
}

function Get-GameFallbackColor {
    param(
        [string]$GameGroup,
        [System.Drawing.Color]$FallbackColor = [System.Drawing.Color]::White
    )

    if ([string]::IsNullOrWhiteSpace($GameGroup)) { return $FallbackColor }
    $palette = @(
        [System.Drawing.Color]::FromArgb(255, 0, 245, 212),
        [System.Drawing.Color]::FromArgb(255, 255, 187, 80),
        [System.Drawing.Color]::FromArgb(255, 139, 247, 168),
        [System.Drawing.Color]::FromArgb(255, 255, 93, 108),
        [System.Drawing.Color]::FromArgb(255, 89, 218, 255),
        [System.Drawing.Color]::FromArgb(255, 255, 126, 54),
        [System.Drawing.Color]::FromArgb(255, 196, 137, 255)
    )
    $hash = Get-GameFallbackHash -GameGroup $GameGroup
    return $palette[[int]($hash % $palette.Count)]
}

function New-StylizedGameFallbackBitmap {
    <#
    .SYNOPSIS
    Creates a deterministic compact game mark for user or catalog game groups
    that do not have a hand-drawn silhouette yet.
    #>
    param(
        [string]$GameGroup,
        [System.Drawing.Color]$Color = [System.Drawing.Color]::White,
        [string]$Category = "Other"
    )

    if ([string]::IsNullOrWhiteSpace($GameGroup)) {
        return New-CategoryBitmap -Category $Category -Color $Color
    }

    $accent = Get-GameFallbackColor -GameGroup $GameGroup -FallbackColor $Color
    $lighter = [System.Drawing.Color]::FromArgb(255,
        [Math]::Min(255, [int]$accent.R + 48),
        [Math]::Min(255, [int]$accent.G + 48),
        [Math]::Min(255, [int]$accent.B + 48)
    )
    $shadow = [System.Drawing.Color]::FromArgb(255,
        [Math]::Max(0, [int]$accent.R - 82),
        [Math]::Max(0, [int]$accent.G - 82),
        [Math]::Max(0, [int]$accent.B - 82)
    )
    $initials = Get-GameFallbackInitials -GameGroup $GameGroup

    $bmp = New-Object System.Drawing.Bitmap(16, 16)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::ClearTypeGridFit
    $g.Clear([System.Drawing.Color]::Transparent)

    $glowBrush = New-Object System.Drawing.SolidBrush(
        [System.Drawing.Color]::FromArgb(42, $accent.R, $accent.G, $accent.B)
    )
    $plateBrush = New-Object System.Drawing.SolidBrush($accent)
    $stripePen = New-Object System.Drawing.Pen($lighter, 1.4)
    $stripePen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
    $stripePen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
    $borderPen = New-Object System.Drawing.Pen($shadow, 1.0)
    $textBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::White)
    $textShadowBrush = New-Object System.Drawing.SolidBrush(
        [System.Drawing.Color]::FromArgb(145, $shadow.R, $shadow.G, $shadow.B)
    )
    $highlightBrush = New-Object System.Drawing.SolidBrush(
        [System.Drawing.Color]::FromArgb(70, 255, 255, 255)
    )
    $sf = New-Object System.Drawing.StringFormat
    $sf.Alignment = [System.Drawing.StringAlignment]::Center
    $sf.LineAlignment = [System.Drawing.StringAlignment]::Center
    $sf.FormatFlags = [System.Drawing.StringFormatFlags]::NoWrap
    $sf.Trimming = [System.Drawing.StringTrimming]::EllipsisCharacter
    $fontSize = if ($initials.Length -ge 2) { 5.4 } else { 7.0 }
    $font = New-Object System.Drawing.Font("Segoe UI Semibold", $fontSize, [System.Drawing.FontStyle]::Bold)

    try {
        $g.FillEllipse($glowBrush, 1, 1, 14, 14)
        $platePoints = [System.Drawing.PointF[]]@(
            (New-Object System.Drawing.PointF(8, 1)),
            (New-Object System.Drawing.PointF(14, 4)),
            (New-Object System.Drawing.PointF(14, 12)),
            (New-Object System.Drawing.PointF(8, 15)),
            (New-Object System.Drawing.PointF(2, 12)),
            (New-Object System.Drawing.PointF(2, 4))
        )
        $g.FillPolygon($plateBrush, $platePoints)
        $g.DrawPolygon($borderPen, $platePoints)
        $g.DrawLine($stripePen, 4, 12, 12, 4)
        $g.FillEllipse($highlightBrush, 5, 3, 4, 3)

        $textRectShadow = New-Object System.Drawing.RectangleF(0.5, 3.2, 16, 9)
        $textRect = New-Object System.Drawing.RectangleF(0, 2.7, 16, 9)
        $g.DrawString($initials, $font, $textShadowBrush, $textRectShadow, $sf)
        $g.DrawString($initials, $font, $textBrush, $textRect, $sf)
    }
    finally {
        $font.Dispose()
        $sf.Dispose()
        $highlightBrush.Dispose()
        $textShadowBrush.Dispose()
        $textBrush.Dispose()
        $borderPen.Dispose()
        $stripePen.Dispose()
        $plateBrush.Dispose()
        $glowBrush.Dispose()
        $g.Dispose()
    }

    return $bmp
}

function New-GameBitmap {
    <#
    .SYNOPSIS
    Creates a 16x16 bitmap with a game-specific icon for a profile's game group.
    Each known game gets a unique silhouette that is instantly recognizable at
    16x16. Unknown non-empty game groups get deterministic monogram marks so
    user/catalog games do not collapse to broad category placeholders.
    .PARAMETER GameGroup
    The game group identifier (e.g. "rivals2", "slippi-melee", "overwatch2").
    .PARAMETER Color
    The category color used for fills and strokes.
    .PARAMETER Category
    Fallback category if the game group has no specific icon.
    #>
    param(
        [string]$GameGroup,
        [System.Drawing.Color]$Color = [System.Drawing.Color]::White,
        [string]$Category = "Other"
    )

    $identity = Get-GameVisualIdentity -GameGroup $GameGroup -FallbackColor $Color
    if (-not $identity.IsKnown) {
        return New-StylizedGameFallbackBitmap -GameGroup $GameGroup -Color $Color -Category $Category
    }

    $gameKey = if ($identity.ContainsKey("Key") -and -not [string]::IsNullOrWhiteSpace("$($identity.Key)")) {
        "$($identity.Key)"
    }
    else {
        "$GameGroup"
    }
    $Color = $identity.Primary

    $bmp = New-Object System.Drawing.Bitmap(16, 16)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $g.Clear([System.Drawing.Color]::Transparent)

    # Shared depth layers
    $glowBrush = New-Object System.Drawing.SolidBrush(
        [System.Drawing.Color]::FromArgb(40, $Color.R, $Color.G, $Color.B)
    )
    $highlightBrush = New-Object System.Drawing.SolidBrush(
        [System.Drawing.Color]::FromArgb(70, 255, 255, 255)
    )
    $lighter = $identity.Secondary
    $darker = $identity.Shadow

    switch ($gameKey) {

        "slippi-melee" {
            # Smash ball: circle with bold cross cutting through it
            # Layer 1: Glow
            $g.FillEllipse($glowBrush, 1, 1, 14, 14)

            # Layer 2: Filled circle
            $fillBrush = New-Object System.Drawing.SolidBrush($Color)
            $g.FillEllipse($fillBrush, 2, 2, 12, 12)
            $fillBrush.Dispose()

            # Cross lines (dark cutout effect through the ball)
            $crossPen = New-Object System.Drawing.Pen($darker, 2.4)
            $crossPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
            $crossPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
            # Horizontal through center
            $g.DrawLine($crossPen, 2, 8, 14, 8)
            # Vertical through center
            $g.DrawLine($crossPen, 8, 2, 8, 14)
            $crossPen.Dispose()

            # Bright center dot
            $centerBrush = New-Object System.Drawing.SolidBrush($lighter)
            $g.FillEllipse($centerBrush, [float]6.5, [float]6.5, [float]3, [float]3)
            $centerBrush.Dispose()

            # Layer 3: Specular
            $g.FillEllipse($highlightBrush, 4, 3, 5, 3)
        }

        "rivals2" {
            # Flame / aether spark: pointed upward teardrop with wisps
            # Layer 1: Glow behind
            $g.FillEllipse($glowBrush, 2, 2, 12, 13)

            # Layer 2: Main flame shape (pointed top, wide rounded bottom)
            $flamePoints = @(
                (New-Object System.Drawing.PointF(8, 1)),       # tip
                (New-Object System.Drawing.PointF(12, 6)),      # right shoulder
                (New-Object System.Drawing.PointF(13, 10)),     # right mid
                (New-Object System.Drawing.PointF(11, 14)),     # right base
                (New-Object System.Drawing.PointF(8, 12)),      # center notch
                (New-Object System.Drawing.PointF(5, 14)),      # left base
                (New-Object System.Drawing.PointF(3, 10)),      # left mid
                (New-Object System.Drawing.PointF(4, 6))        # left shoulder
            )
            $flameBrush = New-Object System.Drawing.SolidBrush($Color)
            $g.FillPolygon($flameBrush, $flamePoints)
            $flameBrush.Dispose()

            # Inner bright core (smaller flame shape)
            $corePoints = @(
                (New-Object System.Drawing.PointF(8, 4)),
                (New-Object System.Drawing.PointF(10.5, 7.5)),
                (New-Object System.Drawing.PointF(10, 11)),
                (New-Object System.Drawing.PointF(8, 9.5)),
                (New-Object System.Drawing.PointF(6, 11)),
                (New-Object System.Drawing.PointF(5.5, 7.5))
            )
            $coreBrush = New-Object System.Drawing.SolidBrush($lighter)
            $g.FillPolygon($coreBrush, $corePoints)
            $coreBrush.Dispose()

            # Layer 3: Specular
            $g.FillEllipse($highlightBrush, 5, 2, 4, 3)
        }

        "overwatch2" {
            # Overwatch shield: circle with bold upward chevron
            # Layer 1: Glow
            $g.FillEllipse($glowBrush, 1, 1, 14, 14)

            # Layer 2: Filled circle
            $circleBrush = New-Object System.Drawing.SolidBrush($Color)
            $g.FillEllipse($circleBrush, 2, 2, 12, 12)
            $circleBrush.Dispose()

            # Chevron cutout (white upward V)
            $chevronPen = New-Object System.Drawing.Pen([System.Drawing.Color]::White, 2.2)
            $chevronPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
            $chevronPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
            $chevronPen.LineJoin = [System.Drawing.Drawing2D.LineJoin]::Round
            $g.DrawLine($chevronPen, 4.5, 10, 8, 5)
            $g.DrawLine($chevronPen, 8, 5, 11.5, 10)
            $chevronPen.Dispose()

            # Layer 3: Specular
            $g.FillEllipse($highlightBrush, 4, 3, 5, 3)
        }

        "fortnite" {
            # Llama face: rounded head shape with ears, simplified piñata icon
            # Layer 1: Glow
            $g.FillEllipse($glowBrush, 2, 2, 12, 13)

            # Layer 2: Head shape (rounded rect body)
            $headBrush = New-Object System.Drawing.SolidBrush($Color)
            $g.FillEllipse($headBrush, 3, 5, 10, 10)     # face
            $headBrush.Dispose()

            # Ears (two small triangles)
            $earBrush = New-Object System.Drawing.SolidBrush($Color)
            $leftEar = @(
                (New-Object System.Drawing.PointF(4, 6)),
                (New-Object System.Drawing.PointF(3, 1)),
                (New-Object System.Drawing.PointF(7, 5))
            )
            $rightEar = @(
                (New-Object System.Drawing.PointF(12, 6)),
                (New-Object System.Drawing.PointF(13, 1)),
                (New-Object System.Drawing.PointF(9, 5))
            )
            $g.FillPolygon($earBrush, $leftEar)
            $g.FillPolygon($earBrush, $rightEar)
            $earBrush.Dispose()

            # Inner ear highlight
            $innerEarBrush = New-Object System.Drawing.SolidBrush($lighter)
            $leftInner = @(
                (New-Object System.Drawing.PointF(4.5, 6)),
                (New-Object System.Drawing.PointF(4, 3)),
                (New-Object System.Drawing.PointF(6, 5.5))
            )
            $rightInner = @(
                (New-Object System.Drawing.PointF(11.5, 6)),
                (New-Object System.Drawing.PointF(12, 3)),
                (New-Object System.Drawing.PointF(10, 5.5))
            )
            $g.FillPolygon($innerEarBrush, $leftInner)
            $g.FillPolygon($innerEarBrush, $rightInner)
            $innerEarBrush.Dispose()

            # Eyes (two dark dots)
            $eyeBrush = New-Object System.Drawing.SolidBrush($darker)
            $g.FillEllipse($eyeBrush, [float]5, [float]8, [float]2.5, [float]2.5)
            $g.FillEllipse($eyeBrush, [float]9, [float]8, [float]2.5, [float]2.5)
            $eyeBrush.Dispose()

            # Layer 3: Specular
            $g.FillEllipse($highlightBrush, 5, 4, 4, 3)
        }

        "marvel-rivals" {
            # Comic diamond burst: central diamond with radiating energy lines
            # Layer 1: Glow
            $g.FillEllipse($glowBrush, 1, 1, 14, 14)

            # Layer 2: Central diamond
            $diamondPoints = @(
                (New-Object System.Drawing.PointF(8, 2)),
                (New-Object System.Drawing.PointF(13, 8)),
                (New-Object System.Drawing.PointF(8, 14)),
                (New-Object System.Drawing.PointF(3, 8))
            )
            $diamondBrush = New-Object System.Drawing.SolidBrush($Color)
            $g.FillPolygon($diamondBrush, $diamondPoints)
            $diamondBrush.Dispose()

            # Inner lighter diamond
            $innerDiamondPoints = @(
                (New-Object System.Drawing.PointF(8, 4.5)),
                (New-Object System.Drawing.PointF(11, 8)),
                (New-Object System.Drawing.PointF(8, 11.5)),
                (New-Object System.Drawing.PointF(5, 8))
            )
            $innerBrush = New-Object System.Drawing.SolidBrush($lighter)
            $g.FillPolygon($innerBrush, $innerDiamondPoints)
            $innerBrush.Dispose()

            # Energy burst lines from corners
            $burstPen = New-Object System.Drawing.Pen(
                [System.Drawing.Color]::FromArgb(120, $Color.R, $Color.G, $Color.B), 1.2
            )
            $burstPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
            $burstPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
            $g.DrawLine($burstPen, 8, 0, 8, 2)
            $g.DrawLine($burstPen, 15, 8, 13, 8)
            $g.DrawLine($burstPen, 8, 16, 8, 14)
            $g.DrawLine($burstPen, 1, 8, 3, 8)
            $burstPen.Dispose()

            # Layer 3: Specular
            $g.FillEllipse($highlightBrush, 5, 3, 4, 3)
        }

        "deadlock" {
            # Occult lock mark: angular shield with a narrow keyhole core.
            # Layer 1: Glow
            $g.FillEllipse($glowBrush, 1, 1, 14, 14)

            # Layer 2: Six-sided lock/shield body
            $lockPoints = @(
                (New-Object System.Drawing.PointF(5, 2)),
                (New-Object System.Drawing.PointF(11, 2)),
                (New-Object System.Drawing.PointF(14, 6)),
                (New-Object System.Drawing.PointF(12, 13)),
                (New-Object System.Drawing.PointF(8, 15)),
                (New-Object System.Drawing.PointF(4, 13)),
                (New-Object System.Drawing.PointF(2, 6))
            )
            $lockBrush = New-Object System.Drawing.SolidBrush($Color)
            $g.FillPolygon($lockBrush, $lockPoints)
            $lockBrush.Dispose()

            # Inner vertical keyhole
            $keyBrush = New-Object System.Drawing.SolidBrush($darker)
            $g.FillEllipse($keyBrush, [float]6, [float]4.5, [float]4, [float]4)
            $g.FillRectangle($keyBrush, 7, 8, 2, 5)
            $keyBrush.Dispose()

            # Split highlight facets for a harder art-deco look
            $facetPen = New-Object System.Drawing.Pen($lighter, 1.1)
            $facetPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
            $facetPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
            $g.DrawLine($facetPen, 5, 3, 3, 6)
            $g.DrawLine($facetPen, 11, 3, 13, 6)
            $g.DrawLine($facetPen, 5, 13, 8, 15)
            $g.DrawLine($facetPen, 11, 13, 8, 15)
            $facetPen.Dispose()

            # Layer 3: Specular
            $g.FillEllipse($highlightBrush, 5, 2, 4, 3)
        }

        "call-of-duty" {
            # Call of Duty: tactical rank chevrons on a compact armor plate.
            # Layer 1: Glow
            $g.FillEllipse($glowBrush, 1, 1, 14, 14)

            # Layer 2: Armor/dogtag plate
            $platePoints = [System.Drawing.PointF[]]@(
                (New-Object System.Drawing.PointF(4, 2)),
                (New-Object System.Drawing.PointF(12, 2)),
                (New-Object System.Drawing.PointF(14, 8)),
                (New-Object System.Drawing.PointF(11, 14)),
                (New-Object System.Drawing.PointF(5, 14)),
                (New-Object System.Drawing.PointF(2, 8))
            )
            $plateBrush = New-Object System.Drawing.SolidBrush($darker)
            $g.FillPolygon($plateBrush, $platePoints)
            $plateBrush.Dispose()

            $platePen = New-Object System.Drawing.Pen($Color, 1.1)
            $platePen.LineJoin = [System.Drawing.Drawing2D.LineJoin]::Round
            $g.DrawPolygon($platePen, $platePoints)
            $platePen.Dispose()

            # Layer 3: stacked chevrons, readable as a tactical shooter mark.
            $chevronPen = New-Object System.Drawing.Pen($lighter, 1.45)
            $chevronPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
            $chevronPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
            $chevronPen.LineJoin = [System.Drawing.Drawing2D.LineJoin]::Round
            $g.DrawLine($chevronPen, 4.6, 5.4, 8, 8.3)
            $g.DrawLine($chevronPen, 8, 8.3, 11.4, 5.4)
            $g.DrawLine($chevronPen, 4.8, 8.2, 8, 11.1)
            $g.DrawLine($chevronPen, 8, 11.1, 11.2, 8.2)
            $chevronPen.Dispose()

            $topBrush = New-Object System.Drawing.SolidBrush($Color)
            $g.FillRectangle($topBrush, 5, 3, 6, 1)
            $topBrush.Dispose()

            # Layer 4: Specular
            $g.FillEllipse($highlightBrush, 5, 2, 4, 2)
        }

        "diablo4" {
            # Gothic crystal gem: downward-pointing faceted gem
            # Layer 1: Glow
            $g.FillEllipse($glowBrush, 2, 1, 12, 14)

            # Layer 2: Gem outline (hexagonal crystal pointing down)
            $gemPoints = @(
                (New-Object System.Drawing.PointF(5, 2)),       # top-left
                (New-Object System.Drawing.PointF(11, 2)),      # top-right
                (New-Object System.Drawing.PointF(13, 5)),      # upper-right
                (New-Object System.Drawing.PointF(8, 14)),      # bottom point
                (New-Object System.Drawing.PointF(3, 5))        # upper-left
            )
            $gemBrush = New-Object System.Drawing.SolidBrush($Color)
            $g.FillPolygon($gemBrush, $gemPoints)
            $gemBrush.Dispose()

            # Facet lines (darker internal lines for gem cuts)
            $facetPen = New-Object System.Drawing.Pen($darker, 1.0)
            $facetPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
            $facetPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
            $g.DrawLine($facetPen, 8, 2, 8, 14)     # center vertical
            $g.DrawLine($facetPen, 5, 2, 8, 7)      # top-left to center
            $g.DrawLine($facetPen, 11, 2, 8, 7)     # top-right to center
            $g.DrawLine($facetPen, 3, 5, 13, 5)     # horizontal crown line
            $facetPen.Dispose()

            # Lighter left facet highlight
            $facetHighlight = @(
                (New-Object System.Drawing.PointF(5, 2)),
                (New-Object System.Drawing.PointF(8, 2)),
                (New-Object System.Drawing.PointF(8, 5))
            )
            $facetBrush = New-Object System.Drawing.SolidBrush($lighter)
            $g.FillPolygon($facetBrush, $facetHighlight)
            $facetBrush.Dispose()

            # Layer 3: Specular
            $g.FillEllipse($highlightBrush, 5, 2, 4, 3)
        }

        "ryujinx-ssbu" {
            # Joy-Con pair: two rounded rectangles side by side
            # Layer 1: Glow
            $g.FillEllipse($glowBrush, 1, 1, 14, 14)

            # Left Joy-Con
            $leftPath = New-Object System.Drawing.Drawing2D.GraphicsPath
            $leftPath.AddArc(1, 2, 4, 4, 180, 90)     # top-left round
            $leftPath.AddLine(3, 2, 7, 2)               # top edge
            $leftPath.AddLine(7, 2, 7, 14)              # right edge
            $leftPath.AddLine(7, 14, 3, 14)             # bottom edge
            $leftPath.AddArc(1, 10, 4, 4, 90, 90)      # bottom-left round
            $leftPath.CloseFigure()
            $leftBrush = New-Object System.Drawing.SolidBrush($Color)
            $g.FillPath($leftBrush, $leftPath)
            $leftBrush.Dispose()
            $leftPath.Dispose()

            # Right Joy-Con
            $rightPath = New-Object System.Drawing.Drawing2D.GraphicsPath
            $rightPath.AddLine(9, 2, 13, 2)
            $rightPath.AddArc(11, 2, 4, 4, 270, 90)    # top-right round
            $rightPath.AddArc(11, 10, 4, 4, 0, 90)     # bottom-right round
            $rightPath.AddLine(13, 14, 9, 14)
            $rightPath.AddLine(9, 14, 9, 2)
            $rightPath.CloseFigure()
            $rightBrush = New-Object System.Drawing.SolidBrush($Color)
            $g.FillPath($rightBrush, $rightPath)
            $rightBrush.Dispose()
            $rightPath.Dispose()

            # Button details: D-pad on left, face buttons on right
            $detailBrush = New-Object System.Drawing.SolidBrush($lighter)
            # Left stick (circle)
            $g.FillEllipse($detailBrush, [float]3, [float]4.5, [float]2.5, [float]2.5)
            # Right buttons (A/B dots)
            $g.FillEllipse($detailBrush, [float]10.5, [float]5, [float]2, [float]2)
            $g.FillEllipse($detailBrush, [float]10.5, [float]9, [float]2, [float]2)
            $detailBrush.Dispose()

            # Center gap line
            $gapPen = New-Object System.Drawing.Pen(
                [System.Drawing.Color]::FromArgb(60, 0, 0, 0), 1.0
            )
            $g.DrawLine($gapPen, 8, 2, 8, 14)
            $gapPen.Dispose()

            # Layer 3: Specular
            $g.FillEllipse($highlightBrush, 3, 2, 5, 3)
        }

        "pokemon-auto-chess" {
            # Pokemon Auto Chess: checker board with a compact pokeball piece.
            # Layer 1: Glow
            $g.FillEllipse($glowBrush, 1, 1, 14, 14)

            # Board base: alternating squares, kept dark so the piece reads.
            $boardBrush = New-Object System.Drawing.SolidBrush($darker)
            $g.FillRectangle($boardBrush, 2, 2, 12, 12)
            $boardBrush.Dispose()

            $tileBrush = New-Object System.Drawing.SolidBrush(
                [System.Drawing.Color]::FromArgb(165, $lighter.R, $lighter.G, $lighter.B)
            )
            $g.FillRectangle($tileBrush, 3, 3, 3, 3)
            $g.FillRectangle($tileBrush, 9, 3, 3, 3)
            $g.FillRectangle($tileBrush, 6, 6, 3, 3)
            $g.FillRectangle($tileBrush, 3, 9, 3, 3)
            $g.FillRectangle($tileBrush, 9, 9, 3, 3)
            $tileBrush.Dispose()

            $boardPen = New-Object System.Drawing.Pen($Color, 1.0)
            $g.DrawRectangle($boardPen, 2, 2, 12, 12)
            $boardPen.Dispose()

            # Foreground piece: pokeball split horizontally with center button.
            $topBrush = New-Object System.Drawing.SolidBrush($Color)
            $g.FillEllipse($topBrush, 4, 4, 8, 8)
            $topBrush.Dispose()

            $bottomBrush = New-Object System.Drawing.SolidBrush($lighter)
            $clipRegion = New-Object System.Drawing.Region(
                (New-Object System.Drawing.RectangleF(0, 8, 16, 8))
            )
            $savedClip = $g.Clip
            $g.Clip = $clipRegion
            $g.FillEllipse($bottomBrush, 4, 4, 8, 8)
            $g.Clip = $savedClip
            $clipRegion.Dispose()
            $bottomBrush.Dispose()

            $bandPen = New-Object System.Drawing.Pen($darker, 1.4)
            $g.DrawLine($bandPen, 4, 8, 12, 8)
            $bandPen.Dispose()

            $btnOutline = New-Object System.Drawing.SolidBrush($darker)
            $g.FillEllipse($btnOutline, [float]6.2, [float]6.2, [float]3.6, [float]3.6)
            $btnOutline.Dispose()
            $btnCenter = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::White)
            $g.FillEllipse($btnCenter, [float]7.0, [float]7.0, [float]2, [float]2)
            $btnCenter.Dispose()

            # Layer 3: Specular
            $g.FillEllipse($highlightBrush, 5, 4, 5, 3)
        }

        "pacdeluxe" {
            # PACDeluxe: native app window wrapped around the Pokemon Auto Chess piece.
            # Layer 1: Glow
            $g.FillEllipse($glowBrush, 1, 1, 14, 14)

            $windowBrush = New-Object System.Drawing.SolidBrush($Color)
            $g.FillRectangle($windowBrush, 2, 3, 12, 10)
            $windowBrush.Dispose()

            $titleBrush = New-Object System.Drawing.SolidBrush($lighter)
            $g.FillRectangle($titleBrush, 3, 4, 10, 2)
            $titleBrush.Dispose()

            $screenBrush = New-Object System.Drawing.SolidBrush($darker)
            $g.FillRectangle($screenBrush, 3, 7, 10, 5)
            $screenBrush.Dispose()

            $gridPen = New-Object System.Drawing.Pen(
                [System.Drawing.Color]::FromArgb(120, $lighter.R, $lighter.G, $lighter.B), 1.0
            )
            $g.DrawLine($gridPen, 6, 7, 6, 12)
            $g.DrawLine($gridPen, 10, 7, 10, 12)
            $g.DrawLine($gridPen, 3, 9, 13, 9)
            $gridPen.Dispose()

            $pieceBrush = New-Object System.Drawing.SolidBrush($lighter)
            $g.FillEllipse($pieceBrush, [float]6.1, [float]7.1, [float]3.8, [float]3.8)
            $pieceBrush.Dispose()

            $pieceBandPen = New-Object System.Drawing.Pen($darker, 1.0)
            $g.DrawLine($pieceBandPen, 6.4, 9, 9.6, 9)
            $pieceBandPen.Dispose()

            $accentPen = New-Object System.Drawing.Pen($Color, 1.2)
            $accentPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
            $accentPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
            $g.DrawLine($accentPen, 4, 13.5, 12, 13.5)
            $accentPen.Dispose()

            # Layer 3: Specular
            $g.FillEllipse($highlightBrush, 4, 4, 5, 2)
        }

        "valorant" {
            # Valorant: twin tactical V shards with a sharp lower point.
            $g.FillEllipse($glowBrush, 1, 1, 14, 14)

            $leftBrush = New-Object System.Drawing.SolidBrush($Color)
            $leftShard = [System.Drawing.PointF[]]@(
                (New-Object System.Drawing.PointF(2.5, 3.0)),
                (New-Object System.Drawing.PointF(6.7, 3.0)),
                (New-Object System.Drawing.PointF(8.0, 10.8)),
                (New-Object System.Drawing.PointF(5.1, 13.0))
            )
            $g.FillPolygon($leftBrush, $leftShard)
            $leftBrush.Dispose()

            $rightBrush = New-Object System.Drawing.SolidBrush($lighter)
            $rightShard = [System.Drawing.PointF[]]@(
                (New-Object System.Drawing.PointF(9.0, 3.0)),
                (New-Object System.Drawing.PointF(13.5, 3.0)),
                (New-Object System.Drawing.PointF(10.9, 13.0)),
                (New-Object System.Drawing.PointF(8.4, 10.8))
            )
            $g.FillPolygon($rightBrush, $rightShard)
            $rightBrush.Dispose()

            $edgePen = New-Object System.Drawing.Pen($darker, 0.95)
            $edgePen.LineJoin = [System.Drawing.Drawing2D.LineJoin]::Round
            $g.DrawPolygon($edgePen, $leftShard)
            $g.DrawPolygon($edgePen, $rightShard)
            $edgePen.Dispose()

            $g.FillEllipse($highlightBrush, 4, 3, 4, 2)
        }

        "apex-legends" {
            # Apex Legends: three-point drop banner over a red arena plate.
            $g.FillEllipse($glowBrush, 1, 1, 14, 14)

            $plateBrush = New-Object System.Drawing.SolidBrush($darker)
            $platePoints = [System.Drawing.PointF[]]@(
                (New-Object System.Drawing.PointF(4, 2)),
                (New-Object System.Drawing.PointF(12, 2)),
                (New-Object System.Drawing.PointF(14, 7)),
                (New-Object System.Drawing.PointF(8, 14)),
                (New-Object System.Drawing.PointF(2, 7))
            )
            $g.FillPolygon($plateBrush, $platePoints)
            $plateBrush.Dispose()

            $bannerBrush = New-Object System.Drawing.SolidBrush($Color)
            $g.FillRectangle($bannerBrush, 4, 3, 8, 3)
            $bannerBrush.Dispose()

            $markPen = New-Object System.Drawing.Pen($lighter, 1.55)
            $markPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
            $markPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
            $g.DrawLine($markPen, 8, 4.5, 4.8, 11.5)
            $g.DrawLine($markPen, 8, 4.5, 11.2, 11.5)
            $g.DrawLine($markPen, 5.8, 9.2, 10.2, 9.2)
            $markPen.Dispose()

            $g.FillEllipse($highlightBrush, 5, 3, 4, 2)
        }

        "counter-strike-2" {
            # Counter-Strike 2: compact crosshair ring with a warm tactical core.
            $g.FillEllipse($glowBrush, 1, 1, 14, 14)

            $ringPen = New-Object System.Drawing.Pen($Color, 1.7)
            $ringPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
            $ringPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
            $g.DrawEllipse($ringPen, 3, 3, 10, 10)
            $ringPen.Dispose()

            $tickPen = New-Object System.Drawing.Pen($lighter, 1.35)
            $tickPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
            $tickPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
            $g.DrawLine($tickPen, 8, 1.8, 8, 5.0)
            $g.DrawLine($tickPen, 8, 11.0, 8, 14.2)
            $g.DrawLine($tickPen, 1.8, 8, 5.0, 8)
            $g.DrawLine($tickPen, 11.0, 8, 14.2, 8)
            $tickPen.Dispose()

            $coreBrush = New-Object System.Drawing.SolidBrush($darker)
            $g.FillEllipse($coreBrush, [float]6.4, [float]6.4, [float]3.2, [float]3.2)
            $coreBrush.Dispose()

            $g.FillEllipse($highlightBrush, 4, 3, 4, 2)
        }

        "rocket-league" {
            # Rocket League: arena shield with a car nose chasing a ball.
            $g.FillEllipse($glowBrush, 1, 1, 14, 14)

            $shieldBrush = New-Object System.Drawing.SolidBrush($darker)
            $shieldPoints = [System.Drawing.PointF[]]@(
                (New-Object System.Drawing.PointF(3, 2)),
                (New-Object System.Drawing.PointF(13, 3)),
                (New-Object System.Drawing.PointF(12, 10)),
                (New-Object System.Drawing.PointF(8, 14)),
                (New-Object System.Drawing.PointF(3, 11))
            )
            $g.FillPolygon($shieldBrush, $shieldPoints)
            $shieldBrush.Dispose()

            $shieldPen = New-Object System.Drawing.Pen($Color, 1.05)
            $g.DrawPolygon($shieldPen, $shieldPoints)
            $shieldPen.Dispose()

            $ballBrush = New-Object System.Drawing.SolidBrush($lighter)
            $g.FillEllipse($ballBrush, [float]9.4, [float]3.4, [float]3.7, [float]3.7)
            $ballBrush.Dispose()

            $carBrush = New-Object System.Drawing.SolidBrush($Color)
            $carPoints = [System.Drawing.PointF[]]@(
                (New-Object System.Drawing.PointF(3.5, 9.5)),
                (New-Object System.Drawing.PointF(8.5, 7.6)),
                (New-Object System.Drawing.PointF(10.7, 9.2)),
                (New-Object System.Drawing.PointF(8.2, 11.2)),
                (New-Object System.Drawing.PointF(4.3, 11.3))
            )
            $g.FillPolygon($carBrush, $carPoints)
            $carBrush.Dispose()

            $wheelBrush = New-Object System.Drawing.SolidBrush($lighter)
            $g.FillEllipse($wheelBrush, [float]4.4, [float]10.5, [float]1.8, [float]1.8)
            $g.FillEllipse($wheelBrush, [float]8.0, [float]9.7, [float]1.8, [float]1.8)
            $wheelBrush.Dispose()

            $g.FillEllipse($highlightBrush, 4, 3, 4, 2)
        }

        "minecraft" {
            # Minecraft: isometric grass block with dirt face and cube edges.
            $g.FillEllipse($glowBrush, 1, 1, 14, 14)

            $topBrush = New-Object System.Drawing.SolidBrush($Color)
            $topFace = [System.Drawing.PointF[]]@(
                (New-Object System.Drawing.PointF(8, 2)),
                (New-Object System.Drawing.PointF(14, 5)),
                (New-Object System.Drawing.PointF(8, 8)),
                (New-Object System.Drawing.PointF(2, 5))
            )
            $g.FillPolygon($topBrush, $topFace)
            $topBrush.Dispose()

            $leftBrush = New-Object System.Drawing.SolidBrush($darker)
            $leftFace = [System.Drawing.PointF[]]@(
                (New-Object System.Drawing.PointF(2, 5)),
                (New-Object System.Drawing.PointF(8, 8)),
                (New-Object System.Drawing.PointF(8, 14)),
                (New-Object System.Drawing.PointF(2, 11))
            )
            $g.FillPolygon($leftBrush, $leftFace)
            $leftBrush.Dispose()

            $rightBrush = New-Object System.Drawing.SolidBrush($lighter)
            $rightFace = [System.Drawing.PointF[]]@(
                (New-Object System.Drawing.PointF(14, 5)),
                (New-Object System.Drawing.PointF(8, 8)),
                (New-Object System.Drawing.PointF(8, 14)),
                (New-Object System.Drawing.PointF(14, 11))
            )
            $g.FillPolygon($rightBrush, $rightFace)
            $rightBrush.Dispose()

            $edgePen = New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb(150, 20, 25, 18), 0.85)
            $g.DrawPolygon($edgePen, $topFace)
            $g.DrawLine($edgePen, 8, 8, 8, 14)
            $g.DrawLine($edgePen, 2, 11, 8, 14)
            $g.DrawLine($edgePen, 14, 11, 8, 14)
            $edgePen.Dispose()

            $g.FillEllipse($highlightBrush, 5, 3, 4, 2)
        }

        "league-of-legends" {
            # League of Legends: ornate crest ring with a cyan river slash.
            $g.FillEllipse($glowBrush, 1, 1, 14, 14)

            $crestBrush = New-Object System.Drawing.SolidBrush($Color)
            $g.FillEllipse($crestBrush, 2, 2, 12, 12)
            $crestBrush.Dispose()

            $innerBrush = New-Object System.Drawing.SolidBrush($darker)
            $g.FillEllipse($innerBrush, 4, 4, 8, 8)
            $innerBrush.Dispose()

            $slashPen = New-Object System.Drawing.Pen($lighter, 1.45)
            $slashPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
            $slashPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
            $g.DrawLine($slashPen, 5, 11, 10.5, 4.5)
            $g.DrawLine($slashPen, 6.3, 11.8, 12, 11.8)
            $slashPen.Dispose()

            $notchBrush = New-Object System.Drawing.SolidBrush($Color)
            $g.FillRectangle($notchBrush, 7, 1, 2, 3)
            $g.FillRectangle($notchBrush, 7, 12, 2, 3)
            $notchBrush.Dispose()

            $g.FillEllipse($highlightBrush, 5, 3, 4, 2)
        }

        "destiny-2" {
            # Destiny 2: tricorn-inspired three-lobed mark with a pale center.
            $g.FillEllipse($glowBrush, 1, 1, 14, 14)

            $backBrush = New-Object System.Drawing.SolidBrush($darker)
            $g.FillEllipse($backBrush, 2, 2, 12, 12)
            $backBrush.Dispose()

            $lobeBrush = New-Object System.Drawing.SolidBrush($Color)
            $g.FillEllipse($lobeBrush, [float]5.2, [float]1.9, [float]5.6, [float]5.6)
            $g.FillEllipse($lobeBrush, [float]2.4, [float]7.0, [float]5.4, [float]5.4)
            $g.FillEllipse($lobeBrush, [float]8.2, [float]7.0, [float]5.4, [float]5.4)
            $lobeBrush.Dispose()

            $cutBrush = New-Object System.Drawing.SolidBrush($darker)
            $g.FillEllipse($cutBrush, [float]6.0, [float]6.0, [float]4.0, [float]4.0)
            $cutBrush.Dispose()

            $coreBrush = New-Object System.Drawing.SolidBrush($lighter)
            $g.FillEllipse($coreBrush, [float]6.8, [float]6.8, [float]2.4, [float]2.4)
            $coreBrush.Dispose()

            $ringPen = New-Object System.Drawing.Pen($lighter, 0.9)
            $g.DrawEllipse($ringPen, 2, 2, 12, 12)
            $ringPen.Dispose()

            $g.FillEllipse($highlightBrush, 5, 3, 4, 2)
        }

        "elden-ring" {
            # Elden Ring: stacked rune rings crossed by a golden sigil stem.
            $g.FillEllipse($glowBrush, 1, 1, 14, 14)

            $darkBrush = New-Object System.Drawing.SolidBrush($darker)
            $g.FillEllipse($darkBrush, 2, 2, 12, 12)
            $darkBrush.Dispose()

            $ringPen = New-Object System.Drawing.Pen($Color, 1.15)
            $ringPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
            $ringPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
            $g.DrawEllipse($ringPen, 3, 2, 8, 8)
            $g.DrawEllipse($ringPen, 5, 4, 8, 8)
            $g.DrawEllipse($ringPen, 3, 6, 8, 8)
            $ringPen.Dispose()

            $stemPen = New-Object System.Drawing.Pen($lighter, 1.25)
            $stemPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
            $stemPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
            $g.DrawLine($stemPen, 8, 2, 8, 14)
            $g.DrawLine($stemPen, 4.2, 11.8, 11.8, 11.8)
            $stemPen.Dispose()

            $g.FillEllipse($highlightBrush, 5, 3, 4, 2)
        }

        "halo-infinite" {
            # Halo Infinite: Spartan helmet visor over an olive armor shell.
            $g.FillEllipse($glowBrush, 1, 1, 14, 14)

            $helmetBrush = New-Object System.Drawing.SolidBrush($Color)
            $helmetPoints = [System.Drawing.PointF[]]@(
                (New-Object System.Drawing.PointF(4, 3)),
                (New-Object System.Drawing.PointF(12, 3)),
                (New-Object System.Drawing.PointF(14, 7)),
                (New-Object System.Drawing.PointF(12, 13)),
                (New-Object System.Drawing.PointF(8, 15)),
                (New-Object System.Drawing.PointF(4, 13)),
                (New-Object System.Drawing.PointF(2, 7))
            )
            $g.FillPolygon($helmetBrush, $helmetPoints)
            $helmetBrush.Dispose()

            $visorBrush = New-Object System.Drawing.SolidBrush($lighter)
            $visorPoints = [System.Drawing.PointF[]]@(
                (New-Object System.Drawing.PointF(4.4, 6.3)),
                (New-Object System.Drawing.PointF(11.6, 6.3)),
                (New-Object System.Drawing.PointF(10.6, 8.5)),
                (New-Object System.Drawing.PointF(5.4, 8.5))
            )
            $g.FillPolygon($visorBrush, $visorPoints)
            $visorBrush.Dispose()

            $mouthPen = New-Object System.Drawing.Pen($darker, 1.1)
            $mouthPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
            $mouthPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
            $g.DrawLine($mouthPen, 5, 11, 11, 11)
            $g.DrawLine($mouthPen, 6.2, 12.5, 9.8, 12.5)
            $mouthPen.Dispose()

            $edgePen = New-Object System.Drawing.Pen($darker, 0.9)
            $edgePen.LineJoin = [System.Drawing.Drawing2D.LineJoin]::Round
            $g.DrawPolygon($edgePen, $helmetPoints)
            $edgePen.Dispose()

            $g.FillEllipse($highlightBrush, 5, 3, 4, 2)
        }

        "cyberpunk-2077" {
            # Cyberpunk 2077: jagged neon shard with cyan glitch rails.
            $g.FillEllipse($glowBrush, 1, 1, 14, 14)

            $boltBrush = New-Object System.Drawing.SolidBrush($Color)
            $boltPoints = [System.Drawing.PointF[]]@(
                (New-Object System.Drawing.PointF(9.5, 1.5)),
                (New-Object System.Drawing.PointF(3.5, 8.3)),
                (New-Object System.Drawing.PointF(7.3, 8.1)),
                (New-Object System.Drawing.PointF(5.6, 14.5)),
                (New-Object System.Drawing.PointF(12.5, 6.8)),
                (New-Object System.Drawing.PointF(8.2, 7.0))
            )
            $g.FillPolygon($boltBrush, $boltPoints)
            $boltBrush.Dispose()

            $edgePen = New-Object System.Drawing.Pen($darker, 0.95)
            $edgePen.LineJoin = [System.Drawing.Drawing2D.LineJoin]::Round
            $g.DrawPolygon($edgePen, $boltPoints)
            $edgePen.Dispose()

            $glitchPen = New-Object System.Drawing.Pen($lighter, 1.15)
            $glitchPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
            $glitchPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
            $g.DrawLine($glitchPen, 2, 4, 6, 4)
            $g.DrawLine($glitchPen, 10, 11, 14, 11)
            $glitchPen.Dispose()

            $g.FillEllipse($highlightBrush, 5, 3, 4, 2)
        }

        "helldivers-2" {
            # Helldivers 2: descending drop pod over a bright tactical star.
            $g.FillEllipse($glowBrush, 1, 1, 14, 14)

            $starBrush = New-Object System.Drawing.SolidBrush($Color)
            $starPoints = [System.Drawing.PointF[]]@(
                (New-Object System.Drawing.PointF(8, 1.5)),
                (New-Object System.Drawing.PointF(9.4, 5.6)),
                (New-Object System.Drawing.PointF(13.8, 5.6)),
                (New-Object System.Drawing.PointF(10.2, 8.2)),
                (New-Object System.Drawing.PointF(11.5, 12.8)),
                (New-Object System.Drawing.PointF(8, 10.1)),
                (New-Object System.Drawing.PointF(4.5, 12.8)),
                (New-Object System.Drawing.PointF(5.8, 8.2)),
                (New-Object System.Drawing.PointF(2.2, 5.6)),
                (New-Object System.Drawing.PointF(6.6, 5.6))
            )
            $g.FillPolygon($starBrush, $starPoints)
            $starBrush.Dispose()

            $podBrush = New-Object System.Drawing.SolidBrush($darker)
            $podPoints = [System.Drawing.PointF[]]@(
                (New-Object System.Drawing.PointF(6.1, 3.4)),
                (New-Object System.Drawing.PointF(9.9, 3.4)),
                (New-Object System.Drawing.PointF(10.8, 9.8)),
                (New-Object System.Drawing.PointF(8, 13.5)),
                (New-Object System.Drawing.PointF(5.2, 9.8))
            )
            $g.FillPolygon($podBrush, $podPoints)
            $podBrush.Dispose()

            $podPen = New-Object System.Drawing.Pen($lighter, 0.95)
            $podPen.LineJoin = [System.Drawing.Drawing2D.LineJoin]::Round
            $g.DrawPolygon($podPen, $podPoints)
            $g.DrawLine($podPen, 8, 4.2, 8, 11.6)
            $podPen.Dispose()

            $g.FillEllipse($highlightBrush, 5, 3, 4, 2)
        }

        "productivity" {
            # Productivity workspace: compact app window with a verified task check.
            # Layer 1: Glow
            $g.FillEllipse($glowBrush, 1, 1, 14, 14)

            # Layer 2: App window frame
            $frameBrush = New-Object System.Drawing.SolidBrush($darker)
            $g.FillRectangle($frameBrush, 3, 3, 10, 9)
            $frameBrush.Dispose()

            $titleBrush = New-Object System.Drawing.SolidBrush($Color)
            $g.FillRectangle($titleBrush, 3, 3, 10, 2)
            $titleBrush.Dispose()

            $paneBrush = New-Object System.Drawing.SolidBrush(
                [System.Drawing.Color]::FromArgb(180, $lighter.R, $lighter.G, $lighter.B)
            )
            $g.FillRectangle($paneBrush, 4, 6, 4, 5)
            $paneBrush.Dispose()

            $linePen = New-Object System.Drawing.Pen($lighter, 1.0)
            $linePen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
            $linePen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
            $g.DrawLine($linePen, 9, 6, 12, 6)
            $g.DrawLine($linePen, 9, 8, 12, 8)
            $linePen.Dispose()

            # Foreground checkmark: the productivity lane is a tray reminder,
            # not a game-apply target.
            $checkPen = New-Object System.Drawing.Pen([System.Drawing.Color]::White, 1.35)
            $checkPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
            $checkPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
            $g.DrawLine($checkPen, 5, 9, 6.5, 10.5)
            $g.DrawLine($checkPen, 6.5, 10.5, 9.5, 7)
            $checkPen.Dispose()

            $standPen = New-Object System.Drawing.Pen($Color, 1.1)
            $standPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
            $standPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
            $g.DrawLine($standPen, 8, 12, 8, 14)
            $g.DrawLine($standPen, 5, 14, 11, 14)
            $standPen.Dispose()

            # Layer 3: Specular
            $g.FillEllipse($highlightBrush, 5, 3, 4, 2)
        }
        default {
            $glowBrush.Dispose()
            $highlightBrush.Dispose()
            $g.Dispose()
            $bmp.Dispose()
            return New-StylizedGameFallbackBitmap -GameGroup $GameGroup -Color $Color -Category $Category
        }
    }

    $glowBrush.Dispose()
    $highlightBrush.Dispose()
    $g.Dispose()
    return $bmp
}

function New-ActiveGameBitmap {
    <#
    .SYNOPSIS
    Creates a game-specific 16x16 profile bitmap with an active-state badge.
    #>
    param(
        [string]$GameGroup,
        [System.Drawing.Color]$Color = [System.Drawing.Color]::White,
        [string]$Category = "Other",
        [string]$ModeBadge = "",
        [bool]$FavoriteBadge = $false,
        [bool]$PendingApplyBadge = $false,
        [bool]$WindowsRestartBadge = $false,
        [bool]$VerificationBadge = $false
    )

    $bmp = New-GameBitmap -GameGroup $GameGroup -Color $Color -Category $Category
    if (-not $bmp) { return $null }

    $normalizedModeBadge = if ([string]::IsNullOrWhiteSpace($ModeBadge)) { "" } else { "$ModeBadge".Trim().ToLowerInvariant() }
    if ($normalizedModeBadge -ne "hdr" -and $normalizedModeBadge -ne "capture") {
        $normalizedModeBadge = ""
    }

    $g = $null
    $shadowBrush = $null
    $badgeBrush = $null
    $shineBrush = $null
    $checkPen = $null
    $pendingPen = $null
    $pendingDotBrush = $null
    $restartPen = $null
    $verifyPen = $null
    $verifyDotBrush = $null
    $modeShadowBrush = $null
    $modeBadgeBrush = $null
    $modeTextBrush = $null
    $modeFont = $null
    $modeFormat = $null
    $modePen = $null
    $starShadowBrush = $null
    $starBrush = $null
    $starPen = $null
    try {
        $g = [System.Drawing.Graphics]::FromImage($bmp)
        $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
        $g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::ClearTypeGridFit

        if ($FavoriteBadge) {
            # Favorite corner badge stays away from the active check.
            $starPoints = [System.Drawing.PointF[]]@(
                (New-Object System.Drawing.PointF(4.0, 0.8)),
                (New-Object System.Drawing.PointF(5.0, 3.0)),
                (New-Object System.Drawing.PointF(7.4, 3.2)),
                (New-Object System.Drawing.PointF(5.6, 4.8)),
                (New-Object System.Drawing.PointF(6.2, 7.1)),
                (New-Object System.Drawing.PointF(4.0, 5.8)),
                (New-Object System.Drawing.PointF(1.8, 7.1)),
                (New-Object System.Drawing.PointF(2.4, 4.8)),
                (New-Object System.Drawing.PointF(0.6, 3.2)),
                (New-Object System.Drawing.PointF(3.0, 3.0))
            )
            $starShadowPoints = [System.Drawing.PointF[]]@(
                (New-Object System.Drawing.PointF(4.4, 1.3)),
                (New-Object System.Drawing.PointF(5.4, 3.5)),
                (New-Object System.Drawing.PointF(7.8, 3.7)),
                (New-Object System.Drawing.PointF(6.0, 5.3)),
                (New-Object System.Drawing.PointF(6.6, 7.6)),
                (New-Object System.Drawing.PointF(4.4, 6.3)),
                (New-Object System.Drawing.PointF(2.2, 7.6)),
                (New-Object System.Drawing.PointF(2.8, 5.3)),
                (New-Object System.Drawing.PointF(1.0, 3.7)),
                (New-Object System.Drawing.PointF(3.4, 3.5))
            )
            $starShadowBrush = New-Object System.Drawing.SolidBrush(
                [System.Drawing.Color]::FromArgb(210, 10, 14, 20)
            )
            $g.FillPolygon($starShadowBrush, $starShadowPoints)
            $starBrush = New-Object System.Drawing.SolidBrush(
                [System.Drawing.Color]::FromArgb(255, 255, 214, 74)
            )
            $g.FillPolygon($starBrush, $starPoints)
            $starPen = New-Object System.Drawing.Pen(
                [System.Drawing.Color]::FromArgb(210, 255, 245, 184), 0.8
            )
            $g.DrawPolygon($starPen, $starPoints)
        }

        if (-not [string]::IsNullOrWhiteSpace($normalizedModeBadge)) {
            # Active rows use the same top-right HDR/capture mode badge as
            # shortcut rows; capture wins over HDR when both are true.
            $modeShadowBrush = New-Object System.Drawing.SolidBrush(
                [System.Drawing.Color]::FromArgb(210, 10, 14, 20)
            )
            $g.FillRectangle($modeShadowBrush, 10, 0, 6, 7)
            $modeColor = if ($normalizedModeBadge -eq "capture") {
                [System.Drawing.Color]::FromArgb(255, 255, 84, 96)
            }
            else {
                [System.Drawing.Color]::FromArgb(255, 96, 165, 250)
            }
            $modeBadgeBrush = New-Object System.Drawing.SolidBrush($modeColor)
            $g.FillRectangle($modeBadgeBrush, 10, 1, 6, 6)
            if ($normalizedModeBadge -eq "capture") {
                $modePen = New-Object System.Drawing.Pen([System.Drawing.Color]::White, 0.9)
                $modePen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
                $modePen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
                $g.DrawEllipse($modePen, [float]11.6, [float]2.5, [float]2.8, [float]2.8)
            }
            else {
                $modeFont = New-Object System.Drawing.Font("Segoe UI", 4.5, [System.Drawing.FontStyle]::Bold)
                $modeTextBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::White)
                $modeFormat = New-Object System.Drawing.StringFormat
                $modeFormat.Alignment = [System.Drawing.StringAlignment]::Center
                $modeFormat.LineAlignment = [System.Drawing.StringAlignment]::Center
                $g.DrawString("H", $modeFont, $modeTextBrush, (New-Object System.Drawing.RectangleF(9.8, 0.6, 6.6, 6.6)), $modeFormat)
            }
        }

        # Compact badge keeps the game silhouette visible while marking active.
        $shadowBrush = New-Object System.Drawing.SolidBrush(
            [System.Drawing.Color]::FromArgb(210, 10, 14, 20)
        )
        $g.FillEllipse($shadowBrush, 7, 7, 9, 9)

        $badgeColor = if ($PendingApplyBadge -or $WindowsRestartBadge) {
            [System.Drawing.Color]::FromArgb(255, 255, 190, 80)
        }
        elseif ($VerificationBadge) {
            [System.Drawing.Color]::FromArgb(255, 80, 170, 255)
        }
        else {
            $Color
        }
        $badgeBrush = New-Object System.Drawing.SolidBrush($badgeColor)
        $g.FillEllipse($badgeBrush, 8, 8, 8, 8)

        $shineBrush = New-Object System.Drawing.SolidBrush(
            [System.Drawing.Color]::FromArgb(90, 255, 255, 255)
        )
        $g.FillEllipse($shineBrush, 9, 9, 3, 2)

        if ($WindowsRestartBadge) {
            $restartPen = New-Object System.Drawing.Pen([System.Drawing.Color]::White, 1.3)
            $restartPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
            $restartPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
            $g.DrawArc($restartPen, [float]9.7, [float]9.7, [float]4.9, [float]4.9, 38, 286)
            $g.DrawLine($restartPen, [float]12.1, [float]9.4, [float]12.1, [float]12.2)
        }
        elseif ($PendingApplyBadge) {
            $pendingPen = New-Object System.Drawing.Pen([System.Drawing.Color]::White, 1.35)
            $pendingPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
            $pendingPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
            $g.DrawLine($pendingPen, [float]12.0, [float]9.8, [float]12.0, [float]12.7)
            $pendingDotBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::White)
            $g.FillEllipse($pendingDotBrush, [float]11.35, [float]13.35, [float]1.3, [float]1.3)
        }
        elseif ($VerificationBadge) {
            $verifyPen = New-Object System.Drawing.Pen([System.Drawing.Color]::White, 1.25)
            $verifyPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
            $verifyPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
            $g.DrawArc($verifyPen, [float]9.9, [float]9.9, [float]4.8, [float]4.8, 205, 290)
            $g.DrawLine($verifyPen, [float]12.0, [float]12.0, [float]14.5, [float]10.6)
            $verifyDotBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::White)
            $g.FillEllipse($verifyDotBrush, [float]11.35, [float]11.35, [float]1.4, [float]1.4)
        }
        else {
            $checkPen = New-Object System.Drawing.Pen([System.Drawing.Color]::White, 1.45)
            $checkPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
            $checkPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
            $g.DrawLine($checkPen, [float]9.8, [float]12.0, [float]11.4, [float]13.6)
            $g.DrawLine($checkPen, [float]11.4, [float]13.6, [float]14.4, [float]9.7)
        }
    }
    finally {
        if ($starPen) { $starPen.Dispose() }
        if ($starBrush) { $starBrush.Dispose() }
        if ($starShadowBrush) { $starShadowBrush.Dispose() }
        if ($modePen) { $modePen.Dispose() }
        if ($modeFormat) { $modeFormat.Dispose() }
        if ($modeFont) { $modeFont.Dispose() }
        if ($modeTextBrush) { $modeTextBrush.Dispose() }
        if ($modeBadgeBrush) { $modeBadgeBrush.Dispose() }
        if ($modeShadowBrush) { $modeShadowBrush.Dispose() }
        if ($restartPen) { $restartPen.Dispose() }
        if ($verifyDotBrush) { $verifyDotBrush.Dispose() }
        if ($verifyPen) { $verifyPen.Dispose() }
        if ($pendingDotBrush) { $pendingDotBrush.Dispose() }
        if ($pendingPen) { $pendingPen.Dispose() }
        if ($checkPen) { $checkPen.Dispose() }
        if ($shineBrush) { $shineBrush.Dispose() }
        if ($badgeBrush) { $badgeBrush.Dispose() }
        if ($shadowBrush) { $shadowBrush.Dispose() }
        if ($g) { $g.Dispose() }
    }

    return $bmp
}

function New-FavoriteGameBitmap {
    <#
    .SYNOPSIS
    Creates a game-specific profile bitmap with a compact favorite star badge.

    .DESCRIPTION
    The star sits in the top-left corner so the bottom-right sync/active area
    stays readable. It composes with New-GameSyncBadgeBitmap when a sync mode is
    supplied, keeping shortcut rows visually dense without replacing the game
    mark.
    #>
    param(
        [string]$GameGroup,
        [System.Drawing.Color]$Color = [System.Drawing.Color]::White,
        [string]$Category = "Other",
        [string]$SyncMode = "agnostic",
        [string]$ModeBadge = ""
    )

    $bmp = New-GameSyncBadgeBitmap -GameGroup $GameGroup -Color $Color -Category $Category -SyncMode $SyncMode -ModeBadge $ModeBadge
    if (-not $bmp) { return $null }

    $g = $null
    $shadowBrush = $null
    $starBrush = $null
    $starPen = $null
    try {
        $g = [System.Drawing.Graphics]::FromImage($bmp)
        $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias

        # Favorite star badge keeps the game/sync mark visible while making
        # shortcut rows identifiable outside the Favorites section.
        $starPoints = [System.Drawing.PointF[]]@(
            (New-Object System.Drawing.PointF(4.0, 0.8)),
            (New-Object System.Drawing.PointF(5.0, 3.0)),
            (New-Object System.Drawing.PointF(7.4, 3.2)),
            (New-Object System.Drawing.PointF(5.6, 4.8)),
            (New-Object System.Drawing.PointF(6.2, 7.1)),
            (New-Object System.Drawing.PointF(4.0, 5.8)),
            (New-Object System.Drawing.PointF(1.8, 7.1)),
            (New-Object System.Drawing.PointF(2.4, 4.8)),
            (New-Object System.Drawing.PointF(0.6, 3.2)),
            (New-Object System.Drawing.PointF(3.0, 3.0))
        )
        $shadowPoints = [System.Drawing.PointF[]]@(
            (New-Object System.Drawing.PointF(4.4, 1.3)),
            (New-Object System.Drawing.PointF(5.4, 3.5)),
            (New-Object System.Drawing.PointF(7.8, 3.7)),
            (New-Object System.Drawing.PointF(6.0, 5.3)),
            (New-Object System.Drawing.PointF(6.6, 7.6)),
            (New-Object System.Drawing.PointF(4.4, 6.3)),
            (New-Object System.Drawing.PointF(2.2, 7.6)),
            (New-Object System.Drawing.PointF(2.8, 5.3)),
            (New-Object System.Drawing.PointF(1.0, 3.7)),
            (New-Object System.Drawing.PointF(3.4, 3.5))
        )

        $shadowBrush = New-Object System.Drawing.SolidBrush(
            [System.Drawing.Color]::FromArgb(210, 10, 14, 20)
        )
        $g.FillPolygon($shadowBrush, $shadowPoints)

        $starColor = [System.Drawing.Color]::FromArgb(255, 255, 214, 74)
        $starBrush = New-Object System.Drawing.SolidBrush($starColor)
        $g.FillPolygon($starBrush, $starPoints)

        $starPen = New-Object System.Drawing.Pen(
            [System.Drawing.Color]::FromArgb(210, 255, 245, 184), 0.8
        )
        $g.DrawPolygon($starPen, $starPoints)
    }
    finally {
        if ($starPen) { $starPen.Dispose() }
        if ($starBrush) { $starBrush.Dispose() }
        if ($shadowBrush) { $shadowBrush.Dispose() }
        if ($g) { $g.Dispose() }
    }

    return $bmp
}

function New-GameMosaicBitmap {
    <#
    .SYNOPSIS
    Creates a compact 16x16 category mosaic from actual game marks.

    .DESCRIPTION
    Category headers use this instead of a broad category placeholder so the
    top-level Profiles menu previews real game identity before a flyout opens.
    #>
    param(
        [string[]]$GameGroups = @(),
        [System.Drawing.Color]$Color = [System.Drawing.Color]::White,
        [string]$Category = "Other"
    )

    $uniqueGroups = [System.Collections.Generic.List[string]]::new()
    $seen = @{}
    foreach ($rawGroup in @($GameGroups)) {
        if ([string]::IsNullOrWhiteSpace("$rawGroup")) { continue }
        $key = "$rawGroup".Trim()
        $lookupKey = $key.ToLowerInvariant()
        if ($seen.ContainsKey($lookupKey)) { continue }
        $seen[$lookupKey] = $true
        [void]$uniqueGroups.Add($key)
        if ($uniqueGroups.Count -ge 3) { break }
    }

    if ($uniqueGroups.Count -eq 0) {
        return New-CategoryBitmap -Category $Category -Color $Color
    }

    $bmp = New-Object System.Drawing.Bitmap(16, 16)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $g.Clear([System.Drawing.Color]::Transparent)

    $baseColor = if ($Color.IsEmpty) { [System.Drawing.Color]::White } else { $Color }
    $glowBrush = New-Object System.Drawing.SolidBrush(
        [System.Drawing.Color]::FromArgb(34, $baseColor.R, $baseColor.G, $baseColor.B)
    )
    $backBrush = New-Object System.Drawing.SolidBrush(
        [System.Drawing.Color]::FromArgb(245, 14, 18, 26)
    )
    $ringPen = New-Object System.Drawing.Pen(
        [System.Drawing.Color]::FromArgb(145, $baseColor.R, $baseColor.G, $baseColor.B), 1
    )
    $cellBackBrush = New-Object System.Drawing.SolidBrush(
        [System.Drawing.Color]::FromArgb(230, 22, 26, 36)
    )
    $cellRingPen = New-Object System.Drawing.Pen(
        [System.Drawing.Color]::FromArgb(120, 255, 255, 255), 0.7
    )

    try {
        $g.FillEllipse($glowBrush, 0, 0, 16, 16)
        $g.FillEllipse($backBrush, 1, 1, 14, 14)
        $g.DrawEllipse($ringPen, 1, 1, 14, 14)

        if ($uniqueGroups.Count -eq 1) {
            $rects = @((New-Object System.Drawing.Rectangle(3, 3, 10, 10)))
        }
        elseif ($uniqueGroups.Count -eq 2) {
            $rects = @(
                (New-Object System.Drawing.Rectangle(1, 3, 8, 8)),
                (New-Object System.Drawing.Rectangle(7, 5, 8, 8))
            )
        }
        else {
            $rects = @(
                (New-Object System.Drawing.Rectangle(1, 2, 7, 7)),
                (New-Object System.Drawing.Rectangle(8, 2, 7, 7)),
                (New-Object System.Drawing.Rectangle(4, 8, 8, 8))
            )
        }

        for ($i = 0; $i -lt $uniqueGroups.Count; $i++) {
            $group = $uniqueGroups[$i]
            $rect = $rects[$i]
            $markColor = $baseColor
            if (Get-Command Get-GameAccentColor -ErrorAction SilentlyContinue) {
                $markColor = Get-GameAccentColor -GameGroup $group -FallbackColor $baseColor
            }

            $g.FillEllipse($cellBackBrush, ($rect.X - 1), ($rect.Y - 1), ($rect.Width + 2), ($rect.Height + 2))
            $mark = New-GameBitmap -GameGroup $group -Color $markColor -Category $Category
            if ($mark) {
                $g.DrawImage($mark, $rect)
                $mark.Dispose()
            }
            $g.DrawEllipse($cellRingPen, ($rect.X - 1), ($rect.Y - 1), ($rect.Width + 2), ($rect.Height + 2))
        }
    }
    finally {
        $cellRingPen.Dispose()
        $cellBackBrush.Dispose()
        $ringPen.Dispose()
        $backBrush.Dispose()
        $glowBrush.Dispose()
        $g.Dispose()
    }

    return $bmp
}

function New-FavoriteGameMosaicBitmap {
    <#
    .SYNOPSIS
    Creates a compact favorite-section mosaic from actual game marks.

    .DESCRIPTION
    Favorites headers should preview the pinned games themselves while still
    carrying the favorite-star affordance that distinguishes the section from
    Recent and category mosaics.
    #>
    param(
        [string[]]$GameGroups = @(),
        [System.Drawing.Color]$Color = [System.Drawing.Color]::White,
        [string]$Category = "Other"
    )

    $bmp = New-GameMosaicBitmap -GameGroups $GameGroups -Color $Color -Category $Category
    if (-not $bmp) { return $null }

    $g = $null
    $starShadowBrush = $null
    $starBrush = $null
    $starPen = $null
    try {
        $g = [System.Drawing.Graphics]::FromImage($bmp)
        $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias

        $starPoints = [System.Drawing.PointF[]]@(
            (New-Object System.Drawing.PointF(4.0, 0.8)),
            (New-Object System.Drawing.PointF(5.0, 3.0)),
            (New-Object System.Drawing.PointF(7.4, 3.2)),
            (New-Object System.Drawing.PointF(5.6, 4.8)),
            (New-Object System.Drawing.PointF(6.2, 7.1)),
            (New-Object System.Drawing.PointF(4.0, 5.8)),
            (New-Object System.Drawing.PointF(1.8, 7.1)),
            (New-Object System.Drawing.PointF(2.4, 4.8)),
            (New-Object System.Drawing.PointF(0.6, 3.2)),
            (New-Object System.Drawing.PointF(3.0, 3.0))
        )
        $shadowPoints = [System.Drawing.PointF[]]@(
            (New-Object System.Drawing.PointF(4.4, 1.3)),
            (New-Object System.Drawing.PointF(5.4, 3.5)),
            (New-Object System.Drawing.PointF(7.8, 3.7)),
            (New-Object System.Drawing.PointF(6.0, 5.3)),
            (New-Object System.Drawing.PointF(6.6, 7.6)),
            (New-Object System.Drawing.PointF(4.4, 6.3)),
            (New-Object System.Drawing.PointF(2.2, 7.6)),
            (New-Object System.Drawing.PointF(2.8, 5.3)),
            (New-Object System.Drawing.PointF(1.0, 3.7)),
            (New-Object System.Drawing.PointF(3.4, 3.5))
        )
        $starShadowBrush = New-Object System.Drawing.SolidBrush(
            [System.Drawing.Color]::FromArgb(230, 10, 14, 20)
        )
        $g.FillPolygon($starShadowBrush, $shadowPoints)

        $starBrush = New-Object System.Drawing.SolidBrush(
            [System.Drawing.Color]::FromArgb(255, 255, 214, 74)
        )
        $g.FillPolygon($starBrush, $starPoints)

        $starPen = New-Object System.Drawing.Pen(
            [System.Drawing.Color]::FromArgb(220, 255, 245, 184), 0.8
        )
        $g.DrawPolygon($starPen, $starPoints)
    }
    finally {
        if ($starPen) { $starPen.Dispose() }
        if ($starBrush) { $starBrush.Dispose() }
        if ($starShadowBrush) { $starShadowBrush.Dispose() }
        if ($g) { $g.Dispose() }
    }

    return $bmp
}

function New-BackupGameMosaicBitmap {
    <#
    .SYNOPSIS
    Creates a compact backup-section mosaic from restorable profile game marks.

    .DESCRIPTION
    Backup headers should show which games have restore points available while
    keeping a small restore affordance so the submenu still reads as Backups.
    #>
    param(
        [string[]]$GameGroups = @(),
        [System.Drawing.Color]$Color = [System.Drawing.Color]::White,
        [string]$Category = "Other"
    )

    $bmp = New-GameMosaicBitmap -GameGroups $GameGroups -Color $Color -Category $Category
    if (-not $bmp) { return $null }

    $g = $null
    $badgeShadowBrush = $null
    $badgeBrush = $null
    $badgeRingPen = $null
    $arrowPen = $null
    try {
        $g = [System.Drawing.Graphics]::FromImage($bmp)
        $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias

        $badgeShadowBrush = New-Object System.Drawing.SolidBrush(
            [System.Drawing.Color]::FromArgb(230, 8, 10, 16)
        )
        $g.FillEllipse($badgeShadowBrush, 7, 7, 9, 9)

        $badgeBase = if ($Color.IsEmpty) { [System.Drawing.Color]::FromArgb(255, 181, 126, 255) } else { $Color }
        $badgeBrush = New-Object System.Drawing.SolidBrush(
            [System.Drawing.Color]::FromArgb(255, $badgeBase.R, $badgeBase.G, $badgeBase.B)
        )
        $g.FillEllipse($badgeBrush, 8, 8, 8, 8)

        $badgeRingPen = New-Object System.Drawing.Pen(
            [System.Drawing.Color]::FromArgb(220, 255, 255, 255), 0.7
        )
        $g.DrawEllipse($badgeRingPen, [float]8.0, [float]8.0, [float]7.6, [float]7.6)

        $arrowPen = New-Object System.Drawing.Pen(
            [System.Drawing.Color]::FromArgb(245, 255, 255, 255), 1.1
        )
        $arrowPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
        $arrowPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
        $g.DrawLine($arrowPen, [float]10.2, [float]11.5, [float]13.6, [float]11.5)
        $g.DrawLine($arrowPen, [float]12.5, [float]10.4, [float]13.8, [float]11.5)
        $g.DrawLine($arrowPen, [float]12.5, [float]12.6, [float]13.8, [float]11.5)
        $g.DrawLine($arrowPen, [float]10.0, [float]9.9, [float]10.0, [float]13.0)
    }
    finally {
        if ($arrowPen) { $arrowPen.Dispose() }
        if ($badgeRingPen) { $badgeRingPen.Dispose() }
        if ($badgeBrush) { $badgeBrush.Dispose() }
        if ($badgeShadowBrush) { $badgeShadowBrush.Dispose() }
        if ($g) { $g.Dispose() }
    }

    return $bmp
}

function New-ActionBitmap {
    <#
    .SYNOPSIS
    Creates a 16x16 bitmap for an action menu item using filled shapes with depth.
    Uses the three-layer depth system: shadow/glow, main fill, specular highlight.
    .PARAMETER Action
    One of: Brand, Actions, Restore, Audit, Refresh, Search, Favorite, Recent, Profiles, Display, Apply, PendingFix, Backups, QuickPanel, Settings, Startup, WindowsRestart, Toast, Sound, Hotkey, Folder, Log, Memory, Reset, Info, Save, Close, Exit
    .PARAMETER Color
    The accent color for this action icon.
    #>
    param(
        [string]$Action,
        [System.Drawing.Color]$Color
    )

    $bmp = New-Object System.Drawing.Bitmap(16, 16)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $g.Clear([System.Drawing.Color]::Transparent)

    # Three-layer depth system shared resources
    $glowBrush = New-Object System.Drawing.SolidBrush(
        [System.Drawing.Color]::FromArgb(40, $Color.R, $Color.G, $Color.B)
    )
    $highlightBrush = New-Object System.Drawing.SolidBrush(
        [System.Drawing.Color]::FromArgb(70, 255, 255, 255)
    )
    $lighter = [System.Drawing.Color]::FromArgb(255,
        [Math]::Min(255, [int]$Color.R + 50),
        [Math]::Min(255, [int]$Color.G + 50),
        [Math]::Min(255, [int]$Color.B + 50)
    )
    $darker = [System.Drawing.Color]::FromArgb(255,
        [Math]::Max(0, [int]$Color.R - 60),
        [Math]::Max(0, [int]$Color.G - 60),
        [Math]::Max(0, [int]$Color.B - 60)
    )

    switch ($Action) {
        "Brand" {
            # A.B.S.O. angular station mark with a small optimizer spark.
            $g.FillEllipse($glowBrush, 1, 1, 14, 14)

            $hexBrush = New-Object System.Drawing.SolidBrush($Color)
            $hexPoints = [System.Drawing.PointF[]]@(
                (New-Object System.Drawing.PointF(8, 1.5)),
                (New-Object System.Drawing.PointF(13.5, 4.6)),
                (New-Object System.Drawing.PointF(13.5, 11.4)),
                (New-Object System.Drawing.PointF(8, 14.5)),
                (New-Object System.Drawing.PointF(2.5, 11.4)),
                (New-Object System.Drawing.PointF(2.5, 4.6))
            )
            $g.FillPolygon($hexBrush, $hexPoints)
            $hexBrush.Dispose()

            $innerBrush = New-Object System.Drawing.SolidBrush($darker)
            $g.FillPolygon($innerBrush, [System.Drawing.PointF[]]@(
                (New-Object System.Drawing.PointF(8, 3.2)),
                (New-Object System.Drawing.PointF(11.7, 5.3)),
                (New-Object System.Drawing.PointF(11.7, 10.7)),
                (New-Object System.Drawing.PointF(8, 12.8)),
                (New-Object System.Drawing.PointF(4.3, 10.7)),
                (New-Object System.Drawing.PointF(4.3, 5.3))
            ))
            $innerBrush.Dispose()

            $aPen = New-Object System.Drawing.Pen($lighter, 1.65)
            $aPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
            $aPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
            $g.DrawLine($aPen, 5.4, 11.2, 8, 4.5)
            $g.DrawLine($aPen, 8, 4.5, 10.6, 11.2)
            $g.DrawLine($aPen, 6.7, 8.7, 9.3, 8.7)
            $aPen.Dispose()

            $sparkBrush = New-Object System.Drawing.SolidBrush($highlightBrush.Color)
            $g.FillEllipse($sparkBrush, 11.1, 3.3, 2.4, 2.4)
            $sparkBrush.Dispose()

            $g.FillEllipse($highlightBrush, 5, 3, 4, 3)
        }
        "Actions" {
            # Stacked command chevrons for primary tray actions.
            $g.FillEllipse($glowBrush, 1, 1, 14, 14)

            $railBrush = New-Object System.Drawing.SolidBrush($Color)
            $g.FillRectangle($railBrush, 3, 3, 2, 10)
            $railBrush.Dispose()

            $linePen = New-Object System.Drawing.Pen($lighter, 1.5)
            $linePen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
            $linePen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
            $g.DrawLine($linePen, 6, 4, 12, 4)
            $g.DrawLine($linePen, 6, 8, 12, 8)
            $g.DrawLine($linePen, 6, 12, 12, 12)
            $linePen.Dispose()

            $arrowBrush = New-Object System.Drawing.SolidBrush($Color)
            $arrowPoints = [System.Drawing.PointF[]]@(
                (New-Object System.Drawing.PointF(11, 5.7)),
                (New-Object System.Drawing.PointF(14, 8)),
                (New-Object System.Drawing.PointF(11, 10.3))
            )
            $g.FillPolygon($arrowBrush, $arrowPoints)
            $arrowBrush.Dispose()

            $sparkBrush = New-Object System.Drawing.SolidBrush($darker)
            $g.FillEllipse($sparkBrush, 2.5, 3.5, 3, 3)
            $sparkBrush.Dispose()

            $g.FillEllipse($highlightBrush, 5, 3, 4, 3)
        }
        "Restore" {
            # Circular undo arrow (arc + filled arrowhead)
            # Layer 1: Glow
            $g.FillEllipse($glowBrush, 1, 1, 14, 14)

            # Layer 2: Circular arc (most of a circle)
            $arcPen = New-Object System.Drawing.Pen($Color, 2.0)
            $arcPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
            $arcPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
            $g.DrawArc($arcPen, 3, 3, 10, 10, 50, 260)
            $arcPen.Dispose()

            # Filled arrowhead triangle (at ~310° pointing CCW/up-left)
            $arrowPoints = @(
                (New-Object System.Drawing.PointF(4, 3)),
                (New-Object System.Drawing.PointF(7.5, 1.5)),
                (New-Object System.Drawing.PointF(7.5, 5.5))
            )
            $arrowBrush = New-Object System.Drawing.SolidBrush($Color)
            $g.FillPolygon($arrowBrush, $arrowPoints)
            $arrowBrush.Dispose()

            # Layer 3: Specular
            $g.FillEllipse($highlightBrush, 5, 4, 4, 3)
        }
        "Audit" {
            # Magnifying glass — bold filled lens + thick handle
            # Layer 1: Glow behind lens
            $g.FillEllipse($glowBrush, 0, 0, 12, 12)

            # Layer 2: Solid filled lens circle
            $lensBrush = New-Object System.Drawing.SolidBrush($Color)
            $g.FillEllipse($lensBrush, 1, 1, 10, 10)
            $lensBrush.Dispose()

            # Glass inner highlight (lighter center for depth)
            $glassBrush = New-Object System.Drawing.SolidBrush(
                [System.Drawing.Color]::FromArgb(50, 255, 255, 255)
            )
            $g.FillEllipse($glassBrush, 3, 3, 6, 6)
            $glassBrush.Dispose()

            # Thick handle to lower-right
            $handlePen = New-Object System.Drawing.Pen($darker, 2.8)
            $handlePen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
            $handlePen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
            $g.DrawLine($handlePen, 10, 10, 14, 14)
            $handlePen.Dispose()

            # Layer 3: Specular
            $g.FillEllipse($highlightBrush, 3, 2, 4, 3)
        }
        "Refresh" {
            # Two circular arrows for profile catalog reload.
            $g.FillEllipse($glowBrush, 1, 1, 14, 14)

            $arcPen = New-Object System.Drawing.Pen($Color, 1.8)
            $arcPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
            $arcPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
            $g.DrawArc($arcPen, 3, 3, 10, 10, 25, 180)
            $g.DrawArc($arcPen, 3, 3, 10, 10, 210, 150)
            $arcPen.Dispose()

            $headOnePoints = [System.Drawing.PointF[]]@(
                (New-Object System.Drawing.PointF(12.7, 2.7)),
                (New-Object System.Drawing.PointF(14.2, 6.1)),
                (New-Object System.Drawing.PointF(10.6, 5.7))
            )
            $headTwoPoints = [System.Drawing.PointF[]]@(
                (New-Object System.Drawing.PointF(3.3, 13.3)),
                (New-Object System.Drawing.PointF(1.8, 9.9)),
                (New-Object System.Drawing.PointF(5.4, 10.3))
            )
            $headBrush = New-Object System.Drawing.SolidBrush($Color)
            $g.FillPolygon($headBrush, $headOnePoints)
            $g.FillPolygon($headBrush, $headTwoPoints)
            $headBrush.Dispose()

            # Layer 3: Specular
            $g.FillEllipse($highlightBrush, 4, 3, 5, 3)
        }
        "Search" {
            # Search result lens with three scan ticks.
            $g.FillEllipse($glowBrush, 1, 1, 14, 14)

            $lensBrush = New-Object System.Drawing.SolidBrush($Color)
            $g.FillEllipse($lensBrush, 2, 2, 9, 9)
            $lensBrush.Dispose()

            $glassBrush = New-Object System.Drawing.SolidBrush(
                [System.Drawing.Color]::FromArgb(60, 255, 255, 255)
            )
            $g.FillEllipse($glassBrush, 4, 4, 4, 4)
            $glassBrush.Dispose()

            $handlePen = New-Object System.Drawing.Pen($darker, 2.4)
            $handlePen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
            $handlePen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
            $g.DrawLine($handlePen, 9, 9, 14, 14)
            $handlePen.Dispose()

            $tickPen = New-Object System.Drawing.Pen($lighter, 1.0)
            $tickPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
            $tickPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
            $g.DrawLine($tickPen, 11, 4, 14, 4)
            $g.DrawLine($tickPen, 12, 6, 14, 6)
            $g.DrawLine($tickPen, 12, 8, 14, 8)
            $tickPen.Dispose()

            $g.FillEllipse($highlightBrush, 4, 3, 4, 3)
        }
        "Favorite" {
            # Filled star for pinned favorite profiles.
            $g.FillEllipse($glowBrush, 1, 1, 14, 14)

            $starPoints = [System.Drawing.PointF[]]@(
                (New-Object System.Drawing.PointF(8, 1.8)),
                (New-Object System.Drawing.PointF(9.7, 5.6)),
                (New-Object System.Drawing.PointF(13.8, 5.9)),
                (New-Object System.Drawing.PointF(10.7, 8.5)),
                (New-Object System.Drawing.PointF(11.7, 12.8)),
                (New-Object System.Drawing.PointF(8, 10.5)),
                (New-Object System.Drawing.PointF(4.3, 12.8)),
                (New-Object System.Drawing.PointF(5.3, 8.5)),
                (New-Object System.Drawing.PointF(2.2, 5.9)),
                (New-Object System.Drawing.PointF(6.3, 5.6))
            )
            $starBrush = New-Object System.Drawing.SolidBrush($Color)
            $g.FillPolygon($starBrush, $starPoints)
            $starBrush.Dispose()

            $edgePen = New-Object System.Drawing.Pen($darker, 1.0)
            $g.DrawPolygon($edgePen, $starPoints)
            $edgePen.Dispose()

            $g.FillEllipse($highlightBrush, 5, 4, 4, 3)
        }
        "Recent" {
            # Clock face with a recent-history sweep arrow.
            $g.FillEllipse($glowBrush, 1, 1, 14, 14)

            $faceBrush = New-Object System.Drawing.SolidBrush($Color)
            $g.FillEllipse($faceBrush, 2, 2, 12, 12)
            $faceBrush.Dispose()

            $handPen = New-Object System.Drawing.Pen($darker, 1.6)
            $handPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
            $handPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
            $g.DrawLine($handPen, 8, 8, 8, 4.5)
            $g.DrawLine($handPen, 8, 8, 11, 9.5)
            $handPen.Dispose()

            $sweepPen = New-Object System.Drawing.Pen($lighter, 1.2)
            $sweepPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
            $sweepPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
            $g.DrawArc($sweepPen, 3, 3, 10, 10, 185, 135)
            $sweepPen.Dispose()

            $headBrush = New-Object System.Drawing.SolidBrush($lighter)
            $headPoints = [System.Drawing.PointF[]]@(
                (New-Object System.Drawing.PointF(3.2, 8.7)),
                (New-Object System.Drawing.PointF(1.8, 5.6)),
                (New-Object System.Drawing.PointF(5, 6.1))
            )
            $g.FillPolygon($headBrush, $headPoints)
            $headBrush.Dispose()

            $g.FillEllipse($highlightBrush, 5, 3, 4, 3)
        }
        "Profiles" {
            # Stacked profile cards for the profile catalog section.
            $g.FillEllipse($glowBrush, 1, 1, 14, 14)

            $backBrush = New-Object System.Drawing.SolidBrush($darker)
            $midBrush = New-Object System.Drawing.SolidBrush($lighter)
            $frontBrush = New-Object System.Drawing.SolidBrush($Color)
            $g.FillRectangle($backBrush, 2, 3, 9, 9)
            $g.FillRectangle($midBrush, 4, 4.8, 9, 9)
            $g.FillRectangle($frontBrush, 6, 6.5, 8, 7)
            $frontBrush.Dispose()
            $midBrush.Dispose()
            $backBrush.Dispose()

            $lineBrush = New-Object System.Drawing.SolidBrush($darker)
            $g.FillRectangle($lineBrush, 7, 8, 5, 1)
            $g.FillRectangle($lineBrush, 7, 10.5, 4, 1)
            $lineBrush.Dispose()

            $g.FillEllipse($highlightBrush, 5, 4, 5, 3)
        }
        "Display" {
            # Display topology monitor with a compact GPU chip.
            $g.FillEllipse($glowBrush, 1, 1, 14, 14)

            $screenBrush = New-Object System.Drawing.SolidBrush($Color)
            $g.FillRectangle($screenBrush, 2, 3, 12, 8)
            $screenBrush.Dispose()

            $screenInnerBrush = New-Object System.Drawing.SolidBrush($darker)
            $g.FillRectangle($screenInnerBrush, 3.5, 4.5, 9, 5)
            $screenInnerBrush.Dispose()

            $signalPen = New-Object System.Drawing.Pen($lighter, 1.2)
            $signalPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
            $signalPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
            $g.DrawLine($signalPen, 5, 7, 7, 5.5)
            $g.DrawLine($signalPen, 7, 5.5, 9, 7.8)
            $g.DrawLine($signalPen, 9, 7.8, 11, 5.8)
            $signalPen.Dispose()

            $standBrush = New-Object System.Drawing.SolidBrush($Color)
            $g.FillRectangle($standBrush, 7, 11, 2, 2)
            $g.FillRectangle($standBrush, 5, 13, 6, 1)
            $standBrush.Dispose()

            $chipBrush = New-Object System.Drawing.SolidBrush($lighter)
            $g.FillRectangle($chipBrush, 10, 10, 4, 4)
            $chipBrush.Dispose()

            $chipLineBrush = New-Object System.Drawing.SolidBrush($darker)
            $g.FillRectangle($chipLineBrush, 11, 11, 2, 2)
            $chipLineBrush.Dispose()

            $g.FillEllipse($highlightBrush, 4, 4, 5, 2)
        }
        "Apply" {
            # Small wrench/check hybrid for targeted remediation actions.
            $g.FillEllipse($glowBrush, 1, 1, 14, 14)

            $stemPen = New-Object System.Drawing.Pen($Color, 2.2)
            $stemPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
            $stemPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
            $g.DrawLine($stemPen, 4, 12, 10, 6)
            $stemPen.Dispose()

            $headBrush = New-Object System.Drawing.SolidBrush($Color)
            $g.FillEllipse($headBrush, 8, 2, 5, 5)
            $headBrush.Dispose()

            $cutBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::Transparent)
            $g.FillEllipse($cutBrush, 10, 3, 3, 3)
            $cutBrush.Dispose()

            $checkPen = New-Object System.Drawing.Pen($lighter, 1.8)
            $checkPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
            $checkPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
            $checkPoints = [System.Drawing.PointF[]]@(
                (New-Object System.Drawing.PointF(2.5, 8.5)),
                (New-Object System.Drawing.PointF(5.0, 11.0)),
                (New-Object System.Drawing.PointF(8.5, 7.0))
            )
            $g.DrawLines($checkPen, $checkPoints)
            $checkPen.Dispose()

            $g.FillEllipse($highlightBrush, 9, 2, 3, 2)
        }
        "PendingFix" {
            # Pending verifier fix: wrench body with an amber exclamation badge.
            $g.FillEllipse($glowBrush, 1, 1, 14, 14)

            $stemPen = New-Object System.Drawing.Pen($Color, 2.15)
            $stemPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
            $stemPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
            $g.DrawLine($stemPen, 4, 12, 10, 6)
            $stemPen.Dispose()

            $headBrush = New-Object System.Drawing.SolidBrush($Color)
            $g.FillEllipse($headBrush, 8, 2, 5, 5)
            $headBrush.Dispose()

            $badgeShadow = New-Object System.Drawing.SolidBrush(
                [System.Drawing.Color]::FromArgb(215, 10, 14, 20)
            )
            $g.FillEllipse($badgeShadow, 1, 7, 8, 8)
            $badgeShadow.Dispose()

            $badgeBrush = New-Object System.Drawing.SolidBrush($lighter)
            $g.FillEllipse($badgeBrush, 2, 8, 7, 7)
            $badgeBrush.Dispose()

            $markPen = New-Object System.Drawing.Pen([System.Drawing.Color]::White, 1.15)
            $markPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
            $markPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
            $g.DrawLine($markPen, [float]5.5, [float]9.7, [float]5.5, [float]12.0)
            $markPen.Dispose()

            $dotBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::White)
            $g.FillEllipse($dotBrush, [float]4.9, [float]12.7, [float]1.2, [float]1.2)
            $dotBrush.Dispose()

            $g.FillEllipse($highlightBrush, 9, 2, 3, 2)
        }
        "Backups" {
            # Three stacked cards/layers with data lines
            # Layer 1: Glow
            $g.FillEllipse($glowBrush, 1, 1, 14, 14)

            # Bottom card (darkest)
            $card3Brush = New-Object System.Drawing.SolidBrush($darker)
            $g.FillRectangle($card3Brush, 4, 6, 10, 8)
            $card3Brush.Dispose()

            # Middle card
            $midColor = [System.Drawing.Color]::FromArgb(255,
                [Math]::Max(0, [int]$Color.R - 30),
                [Math]::Max(0, [int]$Color.G - 30),
                [Math]::Max(0, [int]$Color.B - 30)
            )
            $card2Brush = New-Object System.Drawing.SolidBrush($midColor)
            $g.FillRectangle($card2Brush, 3, 4, 10, 8)
            $card2Brush.Dispose()

            # Top card with gradient
            $topRect = New-Object System.Drawing.Rectangle(2, 2, 10, 8)
            $topBrush = $null
            try {
                $topBrush = New-Object System.Drawing.Drawing2D.LinearGradientBrush(
                    $topRect, $lighter, $Color,
                    [System.Drawing.Drawing2D.LinearGradientMode]::Vertical
                )
            } catch {
                $topBrush = New-Object System.Drawing.SolidBrush($Color)
            }
            $g.FillRectangle($topBrush, $topRect)
            $topBrush.Dispose()

            # Data lines on top card
            $lineBrush = New-Object System.Drawing.SolidBrush(
                [System.Drawing.Color]::FromArgb(180, 255, 255, 255)
            )
            $g.FillRectangle($lineBrush, 4, 4, 6, 1)
            $g.FillRectangle($lineBrush, 4, 6, 4, 1)
            $g.FillRectangle($lineBrush, 4, 8, 5, 1)
            $lineBrush.Dispose()

            # Layer 3: Specular
            $g.FillEllipse($highlightBrush, 3, 2, 5, 3)
        }
        "QuickPanel" {
            # 2x2 grid of filled tiles with varying brightness
            # Layer 1: Glow
            $g.FillEllipse($glowBrush, 1, 1, 14, 14)

            # Layer 2: Four tiles
            $tileBrush1 = New-Object System.Drawing.SolidBrush($lighter)
            $tileBrush2 = New-Object System.Drawing.SolidBrush($Color)
            $tileBrush3 = New-Object System.Drawing.SolidBrush($Color)
            $tileBrush4 = New-Object System.Drawing.SolidBrush($darker)

            $g.FillRectangle($tileBrush1, 2, 2, 5, 5)     # top-left (brightest)
            $g.FillRectangle($tileBrush2, 9, 2, 5, 5)     # top-right
            $g.FillRectangle($tileBrush3, 2, 9, 5, 5)     # bottom-left
            $g.FillRectangle($tileBrush4, 9, 9, 5, 5)     # bottom-right (dimmest)

            $tileBrush1.Dispose()
            $tileBrush2.Dispose()
            $tileBrush3.Dispose()
            $tileBrush4.Dispose()

            # Layer 3: Specular
            $g.FillEllipse($highlightBrush, 3, 2, 4, 3)
        }
        "Settings" {
            # Gear cog (8 teeth + filled body + center hole)
            # Layer 1: Glow
            $g.FillEllipse($glowBrush, 1, 1, 14, 14)

            # Layer 2: 8 rectangular teeth around circle
            [float]$cx = 8.0; [float]$cy = 8.0
            $toothBrush = New-Object System.Drawing.SolidBrush($Color)
            for ($i = 0; $i -lt 8; $i++) {
                [float]$angle = ($i * 45) * [Math]::PI / 180
                [float]$tx = $cx + 5.5 * [Math]::Cos($angle)
                [float]$ty = $cy + 5.5 * [Math]::Sin($angle)
                $g.FillRectangle($toothBrush, ($tx - 1.2), ($ty - 1.2), [float]2.4, [float]2.4)
            }
            $toothBrush.Dispose()

            # Filled circle body with gradient
            $bodyRect = New-Object System.Drawing.Rectangle(3, 3, 10, 10)
            $bodyBrush = $null
            try {
                $bodyBrush = New-Object System.Drawing.Drawing2D.LinearGradientBrush(
                    $bodyRect, $lighter, $Color,
                    [System.Drawing.Drawing2D.LinearGradientMode]::ForwardDiagonal
                )
            } catch {
                $bodyBrush = New-Object System.Drawing.SolidBrush($Color)
            }
            $g.FillEllipse($bodyBrush, $bodyRect)
            $bodyBrush.Dispose()

            # Center hole
            $holeBrush = New-Object System.Drawing.SolidBrush($darker)
            $g.FillEllipse($holeBrush, 6, 6, 4, 4)
            $holeBrush.Dispose()

            # Layer 3: Specular
            $g.FillEllipse($highlightBrush, 4, 3, 5, 3)
        }
        "Startup" {
            # Startup launch arrow from a small Windows tile.
            $g.FillEllipse($glowBrush, 1, 1, 14, 14)

            $tileBrush = New-Object System.Drawing.SolidBrush($Color)
            $g.FillRectangle($tileBrush, 2, 3, 5, 5)
            $g.FillRectangle($tileBrush, 8, 3, 6, 5)
            $g.FillRectangle($tileBrush, 2, 9, 5, 4)
            $g.FillRectangle($tileBrush, 8, 9, 6, 4)
            $tileBrush.Dispose()

            $arrowPen = New-Object System.Drawing.Pen($lighter, 1.8)
            $arrowPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
            $arrowPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
            $g.DrawLine($arrowPen, 5, 12, 11, 6)
            $arrowPen.Dispose()

            $arrowHead = [System.Drawing.PointF[]]@(
                (New-Object System.Drawing.PointF(11, 6)),
                (New-Object System.Drawing.PointF(10, 10)),
                (New-Object System.Drawing.PointF(7, 7))
            )
            $arrowBrush = New-Object System.Drawing.SolidBrush($lighter)
            $g.FillPolygon($arrowBrush, $arrowHead)
            $arrowBrush.Dispose()

            $g.FillEllipse($highlightBrush, 4, 3, 5, 3)
        }
        "WindowsRestart" {
            # Windows reboot-required mark: Windows tile under a circular restart arrow.
            $g.FillEllipse($glowBrush, 1, 1, 14, 14)

            $tileBrush = New-Object System.Drawing.SolidBrush($darker)
            $g.FillRectangle($tileBrush, 3, 4, 4, 3)
            $g.FillRectangle($tileBrush, 8, 4, 5, 3)
            $g.FillRectangle($tileBrush, 3, 8, 4, 4)
            $g.FillRectangle($tileBrush, 8, 8, 5, 4)
            $tileBrush.Dispose()

            $tilePen = New-Object System.Drawing.Pen($Color, 1.0)
            $g.DrawRectangle($tilePen, 3, 4, 10, 8)
            $tilePen.Dispose()

            $arcPen = New-Object System.Drawing.Pen($lighter, 1.55)
            $arcPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
            $arcPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
            $g.DrawArc($arcPen, 3, 2, 10, 10, 210, 285)
            $arcPen.Dispose()

            $headBrush = New-Object System.Drawing.SolidBrush($lighter)
            $headPoints = [System.Drawing.PointF[]]@(
                (New-Object System.Drawing.PointF(12.6, 3.0)),
                (New-Object System.Drawing.PointF(14.2, 6.4)),
                (New-Object System.Drawing.PointF(10.6, 5.9))
            )
            $g.FillPolygon($headBrush, $headPoints)
            $headBrush.Dispose()

            $powerPen = New-Object System.Drawing.Pen([System.Drawing.Color]::White, 1.3)
            $powerPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
            $powerPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
            $g.DrawLine($powerPen, 8, 5, 8, 7.5)
            $powerPen.Dispose()

            $g.FillEllipse($highlightBrush, 4, 3, 5, 2)
        }
        "Toast" {
            # Toast notification bubble with a small status pip.
            $g.FillEllipse($glowBrush, 1, 1, 14, 14)

            $bubbleBrush = New-Object System.Drawing.SolidBrush($Color)
            $g.FillRectangle($bubbleBrush, 2, 3, 12, 9)
            $tailPoints = [System.Drawing.PointF[]]@(
                (New-Object System.Drawing.PointF(5, 12)),
                (New-Object System.Drawing.PointF(7, 12)),
                (New-Object System.Drawing.PointF(4.5, 14))
            )
            $g.FillPolygon($bubbleBrush, $tailPoints)
            $bubbleBrush.Dispose()

            $pipBrush = New-Object System.Drawing.SolidBrush($lighter)
            $g.FillEllipse($pipBrush, 10, 5, 3, 3)
            $pipBrush.Dispose()

            $lineBrush = New-Object System.Drawing.SolidBrush($darker)
            $g.FillRectangle($lineBrush, 4, 6, 5, 1)
            $g.FillRectangle($lineBrush, 4, 9, 7, 1)
            $lineBrush.Dispose()

            $g.FillEllipse($highlightBrush, 4, 4, 5, 2)
        }
        "Sound" {
            # Speaker cone with two sound waves.
            $g.FillEllipse($glowBrush, 1, 1, 14, 14)

            $speakerBrush = New-Object System.Drawing.SolidBrush($Color)
            $speakerPoints = [System.Drawing.PointF[]]@(
                (New-Object System.Drawing.PointF(2.5, 7)),
                (New-Object System.Drawing.PointF(5, 7)),
                (New-Object System.Drawing.PointF(8, 4.5)),
                (New-Object System.Drawing.PointF(8, 11.5)),
                (New-Object System.Drawing.PointF(5, 9)),
                (New-Object System.Drawing.PointF(2.5, 9))
            )
            $g.FillPolygon($speakerBrush, $speakerPoints)
            $speakerBrush.Dispose()

            $wavePen = New-Object System.Drawing.Pen($lighter, 1.4)
            $wavePen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
            $wavePen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
            $g.DrawArc($wavePen, 7, 5, 4, 6, -45, 90)
            $g.DrawArc($wavePen, 9, 3, 5, 10, -45, 90)
            $wavePen.Dispose()

            $g.FillEllipse($highlightBrush, 4, 4, 4, 2)
        }
        "Hotkey" {
            # Keyboard shortcut keycap with a small command spark.
            $g.FillEllipse($glowBrush, 1, 1, 14, 14)

            $keyRect = New-Object System.Drawing.Rectangle(2, 4, 12, 8)
            $keyBrush = $null
            try {
                $keyBrush = New-Object System.Drawing.Drawing2D.LinearGradientBrush(
                    $keyRect,
                    $lighter,
                    $Color,
                    [System.Drawing.Drawing2D.LinearGradientMode]::Vertical
                )
            }
            catch {
                $keyBrush = New-Object System.Drawing.SolidBrush($Color)
            }
            $g.FillRectangle($keyBrush, $keyRect)
            $keyBrush.Dispose()

            $edgePen = New-Object System.Drawing.Pen($darker, 1.0)
            $g.DrawRectangle($edgePen, 2, 4, 12, 8)
            $edgePen.Dispose()

            $glyphPen = New-Object System.Drawing.Pen($darker, 1.2)
            $glyphPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
            $glyphPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
            $g.DrawLine($glyphPen, 5, 8, 7, 6)
            $g.DrawLine($glyphPen, 7, 6, 9, 8)
            $g.DrawLine($glyphPen, 7, 6, 7, 10)
            $glyphPen.Dispose()

            $sparkBrush = New-Object System.Drawing.SolidBrush($highlightBrush.Color)
            $sparkPoints = [System.Drawing.PointF[]]@(
                (New-Object System.Drawing.PointF(11.5, 2.5)),
                (New-Object System.Drawing.PointF(12.4, 4.3)),
                (New-Object System.Drawing.PointF(14.2, 5.0)),
                (New-Object System.Drawing.PointF(12.4, 5.7)),
                (New-Object System.Drawing.PointF(11.5, 7.5)),
                (New-Object System.Drawing.PointF(10.6, 5.7)),
                (New-Object System.Drawing.PointF(8.8, 5.0)),
                (New-Object System.Drawing.PointF(10.6, 4.3))
            )
            $g.FillPolygon($sparkBrush, $sparkPoints)
            $sparkBrush.Dispose()

            $g.FillEllipse($highlightBrush, 4, 5, 5, 2)
        }
        "Folder" {
            # Folder tab with subtle document line.
            $g.FillEllipse($glowBrush, 1, 1, 14, 14)

            $folderBrush = New-Object System.Drawing.SolidBrush($Color)
            $tabPoints = [System.Drawing.PointF[]]@(
                (New-Object System.Drawing.PointF(2, 5)),
                (New-Object System.Drawing.PointF(6, 5)),
                (New-Object System.Drawing.PointF(7.3, 3.2)),
                (New-Object System.Drawing.PointF(10.5, 3.2)),
                (New-Object System.Drawing.PointF(12.5, 5.2)),
                (New-Object System.Drawing.PointF(14, 5.2)),
                (New-Object System.Drawing.PointF(14, 13)),
                (New-Object System.Drawing.PointF(2, 13))
            )
            $g.FillPolygon($folderBrush, $tabPoints)
            $folderBrush.Dispose()

            $lipBrush = New-Object System.Drawing.SolidBrush($lighter)
            $g.FillRectangle($lipBrush, 3, 7, 10, 1)
            $lipBrush.Dispose()

            $g.FillEllipse($highlightBrush, 4, 4, 5, 3)
        }
        "Log" {
            # Log document with two readable lines.
            $g.FillEllipse($glowBrush, 1, 1, 14, 14)

            $pageBrush = New-Object System.Drawing.SolidBrush($Color)
            $g.FillRectangle($pageBrush, 3, 2, 10, 13)
            $pageBrush.Dispose()

            $foldBrush = New-Object System.Drawing.SolidBrush($lighter)
            $foldPoints = [System.Drawing.PointF[]]@(
                (New-Object System.Drawing.PointF(10, 2)),
                (New-Object System.Drawing.PointF(13, 5)),
                (New-Object System.Drawing.PointF(10, 5))
            )
            $g.FillPolygon($foldBrush, $foldPoints)
            $foldBrush.Dispose()

            $lineBrush = New-Object System.Drawing.SolidBrush($darker)
            $g.FillRectangle($lineBrush, 5, 8, 7, 1)
            $g.FillRectangle($lineBrush, 5, 11, 5, 1)
            $lineBrush.Dispose()

            $g.FillEllipse($highlightBrush, 5, 3, 4, 3)
        }
        "Memory" {
            # RAM chip with pins.
            $g.FillEllipse($glowBrush, 1, 1, 14, 14)

            $chipBrush = New-Object System.Drawing.SolidBrush($Color)
            $g.FillRectangle($chipBrush, 3, 4, 10, 8)
            $chipBrush.Dispose()

            $pinPen = New-Object System.Drawing.Pen($lighter, 1)
            for ($x = 4; $x -le 12; $x += 3) {
                $g.DrawLine($pinPen, $x, 3, $x, 4)
                $g.DrawLine($pinPen, $x, 12, $x, 13)
            }
            $pinPen.Dispose()

            $coreBrush = New-Object System.Drawing.SolidBrush($darker)
            $g.FillRectangle($coreBrush, 5, 6, 6, 4)
            $coreBrush.Dispose()

            $g.FillEllipse($highlightBrush, 5, 4, 5, 2)
        }
        "Reset" {
            # High-impact display recovery mark: bolt inside warning ring.
            $g.FillEllipse($glowBrush, 1, 1, 14, 14)

            $ringPen = New-Object System.Drawing.Pen($Color, 1.8)
            $g.DrawEllipse($ringPen, 2, 2, 12, 12)
            $ringPen.Dispose()

            $boltBrush = New-Object System.Drawing.SolidBrush($lighter)
            $boltPoints = [System.Drawing.PointF[]]@(
                (New-Object System.Drawing.PointF(9, 2.5)),
                (New-Object System.Drawing.PointF(5.5, 8)),
                (New-Object System.Drawing.PointF(8, 8)),
                (New-Object System.Drawing.PointF(6.8, 13.5)),
                (New-Object System.Drawing.PointF(11.5, 6.8)),
                (New-Object System.Drawing.PointF(8.5, 6.8))
            )
            $g.FillPolygon($boltBrush, $boltPoints)
            $boltBrush.Dispose()

            $g.FillEllipse($highlightBrush, 4, 3, 5, 3)
        }
        "Info" {
            # Information dot for About/help surfaces.
            $g.FillEllipse($glowBrush, 1, 1, 14, 14)

            $bodyBrush = New-Object System.Drawing.SolidBrush($Color)
            $g.FillEllipse($bodyBrush, 2, 2, 12, 12)
            $bodyBrush.Dispose()

            $markBrush = New-Object System.Drawing.SolidBrush($darker)
            $g.FillEllipse($markBrush, [float]7, [float]4, [float]2, [float]2)
            $g.FillRectangle($markBrush, 7, 7, 2, 6)
            $markBrush.Dispose()

            $g.FillEllipse($highlightBrush, 4, 3, 5, 3)
        }
        "Save" {
            # Compact disk/save glyph with an applied-settings check.
            $g.FillEllipse($glowBrush, 1, 1, 14, 14)

            $bodyBrush = New-Object System.Drawing.SolidBrush($Color)
            $g.FillRectangle($bodyBrush, 3, 2, 10, 12)
            $bodyBrush.Dispose()

            $slotBrush = New-Object System.Drawing.SolidBrush($darker)
            $g.FillRectangle($slotBrush, 5, 3, 6, 3)
            $g.FillRectangle($slotBrush, 5, 10, 6, 3)
            $slotBrush.Dispose()

            $labelBrush = New-Object System.Drawing.SolidBrush($lighter)
            $g.FillRectangle($labelBrush, 6, 11, 4, 1)
            $labelBrush.Dispose()

            $checkPen = New-Object System.Drawing.Pen([System.Drawing.Color]::White, 1.45)
            $checkPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
            $checkPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
            $g.DrawLine($checkPen, 5, 8, 7, 10)
            $g.DrawLine($checkPen, 7, 10, 11, 6)
            $checkPen.Dispose()

            $g.FillEllipse($highlightBrush, 5, 3, 4, 2)
        }
        "Close" {
            # Window close X inside a quiet control disc.
            $g.FillEllipse($glowBrush, 1, 1, 14, 14)

            $discBrush = New-Object System.Drawing.SolidBrush($Color)
            $g.FillEllipse($discBrush, 2, 2, 12, 12)
            $discBrush.Dispose()

            $xPen = New-Object System.Drawing.Pen($darker, 2.0)
            $xPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
            $xPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
            $g.DrawLine($xPen, 5, 5, 11, 11)
            $g.DrawLine($xPen, 11, 5, 5, 11)
            $xPen.Dispose()

            $g.FillEllipse($highlightBrush, 4, 3, 5, 3)
        }
        "Warning" {
            # Filled warning triangle with exclamation mark.
            $g.FillEllipse($glowBrush, 1, 1, 14, 14)

            $triPoints = [System.Drawing.PointF[]]@(
                (New-Object System.Drawing.PointF(8, 2)),
                (New-Object System.Drawing.PointF(14, 13)),
                (New-Object System.Drawing.PointF(2, 13))
            )
            $triBrush = $null
            try {
                $triBrush = New-Object System.Drawing.Drawing2D.LinearGradientBrush(
                    (New-Object System.Drawing.Rectangle(2, 2, 12, 11)),
                    $lighter,
                    $Color,
                    [System.Drawing.Drawing2D.LinearGradientMode]::Vertical
                )
            }
            catch {
                $triBrush = New-Object System.Drawing.SolidBrush($Color)
            }
            $g.FillPolygon($triBrush, $triPoints)
            $triBrush.Dispose()

            $borderPen = New-Object System.Drawing.Pen($darker, 1.0)
            $g.DrawPolygon($borderPen, $triPoints)
            $borderPen.Dispose()

            $markPen = New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb(230, 20, 22, 28), 1.6)
            $markPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
            $markPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
            $g.DrawLine($markPen, 8, 5, 8, 9)
            $markPen.Dispose()

            $markBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(230, 20, 22, 28))
            $g.FillEllipse($markBrush, [float]7.2, [float]10.6, [float]1.6, [float]1.6)
            $markBrush.Dispose()

            $g.FillEllipse($highlightBrush, 5, 3, 5, 3)
        }
        "Exit" {
            # IEC power symbol (open circle arc + vertical line)
            # Layer 1: Glow
            $g.FillEllipse($glowBrush, 2, 2, 12, 12)

            # Layer 2: Open circle arc (gap at top)
            $arcPen = New-Object System.Drawing.Pen($Color, 1.8)
            $arcPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
            $arcPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
            $g.DrawArc($arcPen, 3, 4, 10, 10, 50, 260)
            $arcPen.Dispose()

            # Vertical line through gap
            $linePen = New-Object System.Drawing.Pen($Color, 1.8)
            $linePen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
            $linePen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
            $g.DrawLine($linePen, 8, 2, 8, 8)
            $linePen.Dispose()

            # Layer 3: Specular
            $g.FillEllipse($highlightBrush, 4, 3, 5, 3)
        }
    }

    $glowBrush.Dispose()
    $highlightBrush.Dispose()
    $g.Dispose()
    return $bmp
}

function New-ActiveCheckBitmap {
    <#
    .SYNOPSIS
    Creates a 16x16 bitmap with a category-colored filled circle, white checkmark, and outer glow ring.
    Used to mark the currently active profile.
    .PARAMETER Color
    The category color for the circle and glow.
    #>
    param([System.Drawing.Color]$Color)

    $bmp = New-Object System.Drawing.Bitmap(16, 16)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $g.Clear([System.Drawing.Color]::Transparent)

    # Outer glow ring
    $glowBrush = New-Object System.Drawing.SolidBrush(
        [System.Drawing.Color]::FromArgb(50, $Color.R, $Color.G, $Color.B)
    )
    $g.FillEllipse($glowBrush, 0, 0, 15, 15)
    $glowBrush.Dispose()

    # Main filled circle
    $mainBrush = New-Object System.Drawing.SolidBrush($Color)
    $g.FillEllipse($mainBrush, 2, 2, 12, 12)
    $mainBrush.Dispose()

    # White checkmark
    $pen = New-Object System.Drawing.Pen([System.Drawing.Color]::White, 1.8)
    $pen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
    $pen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
    $g.DrawLine($pen, 5, 8, 7, 10.5)
    $g.DrawLine($pen, 7, 10.5, 11, 5.5)
    $pen.Dispose()

    # Specular highlight
    $highlightBrush = New-Object System.Drawing.SolidBrush(
        [System.Drawing.Color]::FromArgb(70, 255, 255, 255)
    )
    $g.FillEllipse($highlightBrush, 4, 3, 5, 3)
    $highlightBrush.Dispose()

    $g.Dispose()
    return $bmp
}

function New-AuditStatusBitmap {
    <#
    .SYNOPSIS
    Creates the audit-status row icon. Issue states keep the audit lens visible
    while adding a compact amber badge instead of falling back to a generic
    warning triangle.
    #>
    param(
        [System.Drawing.Color]$Color = [System.Drawing.Color]::White,
        [switch]$IssueBadge
    )

    $bmp = New-ActionBitmap -Action "Audit" -Color $Color
    if (-not $bmp -or -not $IssueBadge) { return $bmp }

    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias

    $shadowBrush = New-Object System.Drawing.SolidBrush(
        [System.Drawing.Color]::FromArgb(220, 10, 14, 20)
    )
    $badgeBrush = New-Object System.Drawing.SolidBrush(
        [System.Drawing.Color]::FromArgb(255, 245, 120, 92)
    )
    $textBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::White)
    $markPen = New-Object System.Drawing.Pen([System.Drawing.Color]::White, 1.05)
    $markPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
    $markPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round

    try {
        $g.FillEllipse($shadowBrush, 8, 0, 8, 8)
        $g.FillEllipse($badgeBrush, 9, 1, 7, 7)
        $g.DrawLine($markPen, [float]12.5, [float]2.4, [float]12.5, [float]5.0)
        $g.FillEllipse($textBrush, [float]11.9, [float]5.8, [float]1.2, [float]1.2)
    }
    finally {
        $markPen.Dispose()
        $textBrush.Dispose()
        $badgeBrush.Dispose()
        $shadowBrush.Dispose()
        $g.Dispose()
    }

    return $bmp
}

function New-SyncBadgeImage {
    <#
    .SYNOPSIS
    Creates a 16x16 bitmap badge for sync mode display on menu items.
    .PARAMETER SyncMode
    "on" = G-SYNC/VRR (NVIDIA green pill with white "G"),
    "off" = No-Sync (amber pill with white prohibition symbol).
    Returns $null for "agnostic" or unknown modes.
    #>
    param([string]$SyncMode)

    if ($SyncMode -ne "on" -and $SyncMode -ne "off") { return $null }

    $bmp = New-Object System.Drawing.Bitmap(16, 16)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $g.Clear([System.Drawing.Color]::Transparent)

    if ($SyncMode -eq "on") {
        # G-SYNC badge: NVIDIA green (#76B900) rounded pill with white "G"
        $bgBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(255, 118, 185, 0))
        # Draw rounded pill shape
        $g.FillEllipse($bgBrush, 0, 1, 6, 6)
        $g.FillEllipse($bgBrush, 10, 1, 6, 6)
        $g.FillEllipse($bgBrush, 0, 9, 6, 6)
        $g.FillEllipse($bgBrush, 10, 9, 6, 6)
        $g.FillRectangle($bgBrush, 3, 1, 10, 14)
        $g.FillRectangle($bgBrush, 0, 4, 16, 8)

        # White "G" — instantly recognizable as G-SYNC
        $font = New-Object System.Drawing.Font("Segoe UI", 8.5, [System.Drawing.FontStyle]::Bold)
        $textBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::White)
        $sf = New-Object System.Drawing.StringFormat
        $sf.Alignment = [System.Drawing.StringAlignment]::Center
        $sf.LineAlignment = [System.Drawing.StringAlignment]::Center
        $rect = New-Object System.Drawing.RectangleF(0, 0, 16, 16)
        $g.DrawString("G", $font, $textBrush, $rect, $sf)
        $font.Dispose()
        $textBrush.Dispose()
        $sf.Dispose()
        $bgBrush.Dispose()
    }
    else {
        # No-Sync badge: Amber pill with white circle-slash (prohibition symbol)
        $bgBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(255, 210, 150, 40))
        # Draw rounded pill shape
        $g.FillEllipse($bgBrush, 0, 1, 6, 6)
        $g.FillEllipse($bgBrush, 10, 1, 6, 6)
        $g.FillEllipse($bgBrush, 0, 9, 6, 6)
        $g.FillEllipse($bgBrush, 10, 9, 6, 6)
        $g.FillRectangle($bgBrush, 3, 1, 10, 14)
        $g.FillRectangle($bgBrush, 0, 4, 16, 8)

        # White circle with diagonal slash — universal "off/disabled"
        $pen = New-Object System.Drawing.Pen([System.Drawing.Color]::White, 1.6)
        $pen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
        $pen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
        $g.DrawEllipse($pen, 3, 3, 10, 10)
        $g.DrawLine($pen, 5, 5, 11, 11)
        $pen.Dispose()
        $bgBrush.Dispose()
    }

    $g.Dispose()
    return $bmp
}

function New-GameSyncBadgeBitmap {
    <#
    .SYNOPSIS
    Creates a game-specific 16x16 bitmap with a compact sync-mode badge.

    The badge is deliberately small so flyout variant rows keep the game mark
    visible instead of replacing it with a generic sync pill.
    #>
    param(
        [string]$GameGroup,
        [System.Drawing.Color]$Color = [System.Drawing.Color]::White,
        [string]$Category = "Other",
        [string]$SyncMode = "agnostic",
        [string]$ModeBadge = ""
    )

    $bmp = New-GameBitmap -GameGroup $GameGroup -Color $Color -Category $Category
    if (-not $bmp) { return $null }

    $normalizedModeBadge = if ([string]::IsNullOrWhiteSpace($ModeBadge)) { "" } else { "$ModeBadge".Trim().ToLowerInvariant() }
    if ($normalizedModeBadge -ne "hdr" -and $normalizedModeBadge -ne "capture") {
        $normalizedModeBadge = ""
    }
    $hasSyncBadge = ($SyncMode -eq "on" -or $SyncMode -eq "off")
    if (-not $hasSyncBadge -and [string]::IsNullOrWhiteSpace($normalizedModeBadge)) { return $bmp }

    $g = $null
    $shadowBrush = $null
    $badgeBrush = $null
    $shineBrush = $null
    $textBrush = $null
    $font = $null
    $format = $null
    $pen = $null
    $modeShadowBrush = $null
    $modeBadgeBrush = $null
    $modeTextBrush = $null
    $modeFont = $null
    $modeFormat = $null
    $modePen = $null
    try {
        $g = [System.Drawing.Graphics]::FromImage($bmp)
        $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
        $g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::ClearTypeGridFit

        if ($hasSyncBadge) {
            # Game-sync badge keeps the game silhouette visible while marking sync mode.
            $shadowBrush = New-Object System.Drawing.SolidBrush(
                [System.Drawing.Color]::FromArgb(220, 10, 14, 20)
            )
            $g.FillEllipse($shadowBrush, 7, 7, 9, 9)

            $badgeColor = if ($SyncMode -eq "on") {
                [System.Drawing.Color]::FromArgb(255, 118, 185, 0)
            }
            else {
                [System.Drawing.Color]::FromArgb(255, 210, 150, 40)
            }
            $badgeBrush = New-Object System.Drawing.SolidBrush($badgeColor)
            $g.FillEllipse($badgeBrush, 8, 8, 8, 8)

            $shineBrush = New-Object System.Drawing.SolidBrush(
                [System.Drawing.Color]::FromArgb(80, 255, 255, 255)
            )
            $g.FillEllipse($shineBrush, 9, 9, 3, 2)

            if ($SyncMode -eq "on") {
                $font = New-Object System.Drawing.Font("Segoe UI", 4.8, [System.Drawing.FontStyle]::Bold)
                $textBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::White)
                $format = New-Object System.Drawing.StringFormat
                $format.Alignment = [System.Drawing.StringAlignment]::Center
                $format.LineAlignment = [System.Drawing.StringAlignment]::Center
                $g.DrawString("G", $font, $textBrush, (New-Object System.Drawing.RectangleF(7.7, 7.4, 8.4, 8.4)), $format)
            }
            else {
                $pen = New-Object System.Drawing.Pen([System.Drawing.Color]::White, 1.05)
                $pen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
                $pen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
                $g.DrawEllipse($pen, [float]9.4, [float]9.4, [float]5.2, [float]5.2)
                $g.DrawLine($pen, [float]10.4, [float]10.4, [float]13.7, [float]13.7)
            }
        }

        if (-not [string]::IsNullOrWhiteSpace($normalizedModeBadge)) {
            # Mode badge uses the top-right corner so favorite stars and sync
            # badges remain legible. Capture wins over HDR when both are true.
            $modeShadowBrush = New-Object System.Drawing.SolidBrush(
                [System.Drawing.Color]::FromArgb(210, 10, 14, 20)
            )
            $g.FillRectangle($modeShadowBrush, 10, 0, 6, 7)

            $modeColor = if ($normalizedModeBadge -eq "capture") {
                [System.Drawing.Color]::FromArgb(255, 255, 84, 96)
            }
            else {
                [System.Drawing.Color]::FromArgb(255, 96, 165, 250)
            }
            $modeBadgeBrush = New-Object System.Drawing.SolidBrush($modeColor)
            $g.FillRectangle($modeBadgeBrush, 10, 1, 6, 6)

            if ($normalizedModeBadge -eq "capture") {
                $modePen = New-Object System.Drawing.Pen([System.Drawing.Color]::White, 0.9)
                $modePen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
                $modePen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
                $g.DrawEllipse($modePen, [float]11.6, [float]2.5, [float]2.8, [float]2.8)
            }
            else {
                $modeFont = New-Object System.Drawing.Font("Segoe UI", 4.5, [System.Drawing.FontStyle]::Bold)
                $modeTextBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::White)
                $modeFormat = New-Object System.Drawing.StringFormat
                $modeFormat.Alignment = [System.Drawing.StringAlignment]::Center
                $modeFormat.LineAlignment = [System.Drawing.StringAlignment]::Center
                $g.DrawString("H", $modeFont, $modeTextBrush, (New-Object System.Drawing.RectangleF(9.8, 0.6, 6.6, 6.6)), $modeFormat)
            }
        }
    }
    finally {
        if ($modePen) { $modePen.Dispose() }
        if ($modeFormat) { $modeFormat.Dispose() }
        if ($modeFont) { $modeFont.Dispose() }
        if ($modeTextBrush) { $modeTextBrush.Dispose() }
        if ($modeBadgeBrush) { $modeBadgeBrush.Dispose() }
        if ($modeShadowBrush) { $modeShadowBrush.Dispose() }
        if ($pen) { $pen.Dispose() }
        if ($format) { $format.Dispose() }
        if ($font) { $font.Dispose() }
        if ($textBrush) { $textBrush.Dispose() }
        if ($shineBrush) { $shineBrush.Dispose() }
        if ($badgeBrush) { $badgeBrush.Dispose() }
        if ($shadowBrush) { $shadowBrush.Dispose() }
        if ($g) { $g.Dispose() }
    }

    return $bmp
}
