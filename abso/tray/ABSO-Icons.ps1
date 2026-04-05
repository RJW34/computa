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
    One of: Fighting, ARPG, Shooter, Productivity, Streaming, Other
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
    One of: Fighting, ARPG, Shooter, Productivity, Streaming, Other
    .PARAMETER Color
    The category color for fills and strokes.
    #>
    param(
        [string]$Category,
        [System.Drawing.Color]$Color = [System.Drawing.Color]::White
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

    switch ($Category) {
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
            $points = @(
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
            $diamondPoints = @(
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

function New-GameBitmap {
    <#
    .SYNOPSIS
    Creates a 16x16 bitmap with a game-specific icon for a profile's game group.
    Each game gets a unique silhouette that is instantly recognizable at 16x16.
    Falls back to the category icon for unknown games.
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

    # Dispatch to known game icons; fall back to category for unknown games
    $known = @(
        "slippi-melee", "rivals2", "overwatch2", "cod-bo7", "fortnite",
        "marvel-rivals", "diablo4", "ryujinx-ssbu", "pokemon-auto-chess",
        "pacdeluxe", "productivity"
    )
    if ($GameGroup -notin $known) {
        return New-CategoryBitmap -Category $Category -Color $Color
    }

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

    switch ($GameGroup) {

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

        "cod-bo7" {
            # Military 5-pointed star emblem
            # Layer 1: Glow
            $g.FillEllipse($glowBrush, 1, 1, 14, 14)

            # Layer 2: Filled 5-pointed star
            [float]$cx = 8.0; [float]$cy = 8.0
            [float]$outerR = 6.5; [float]$innerR = 2.8
            $starPoints = @()
            for ($i = 0; $i -lt 10; $i++) {
                [float]$angle = ($i * 36 - 90) * [Math]::PI / 180
                [float]$r = if ($i % 2 -eq 0) { $outerR } else { $innerR }
                $starPoints += New-Object System.Drawing.PointF(
                    ($cx + $r * [Math]::Cos($angle)),
                    ($cy + $r * [Math]::Sin($angle))
                )
            }
            $starBrush = New-Object System.Drawing.SolidBrush($Color)
            $g.FillPolygon($starBrush, $starPoints)
            $starBrush.Dispose()

            # Inner lighter star
            $innerStarPoints = @()
            for ($i = 0; $i -lt 10; $i++) {
                [float]$angle = ($i * 36 - 90) * [Math]::PI / 180
                [float]$r = if ($i % 2 -eq 0) { 4.0 } else { 1.8 }
                $innerStarPoints += New-Object System.Drawing.PointF(
                    ($cx + $r * [Math]::Cos($angle)),
                    ($cy + $r * [Math]::Sin($angle))
                )
            }
            $innerBrush = New-Object System.Drawing.SolidBrush($lighter)
            $g.FillPolygon($innerBrush, $innerStarPoints)
            $innerBrush.Dispose()

            # Layer 3: Specular
            $g.FillEllipse($highlightBrush, 5, 2, 4, 3)
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
            # Pokeball: circle split horizontally with center button
            # Layer 1: Glow
            $g.FillEllipse($glowBrush, 1, 1, 14, 14)

            # Layer 2: Top half (main color)
            $topBrush = New-Object System.Drawing.SolidBrush($Color)
            $g.FillEllipse($topBrush, 2, 2, 12, 12)
            $topBrush.Dispose()

            # Bottom half (lighter)
            $bottomBrush = New-Object System.Drawing.SolidBrush($lighter)
            $clipRegion = New-Object System.Drawing.Region(
                (New-Object System.Drawing.RectangleF(0, 8, 16, 8))
            )
            $savedClip = $g.Clip
            $g.Clip = $clipRegion
            $g.FillEllipse($bottomBrush, 2, 2, 12, 12)
            $g.Clip = $savedClip
            $clipRegion.Dispose()
            $bottomBrush.Dispose()

            # Center band (dark horizontal line through middle)
            $bandPen = New-Object System.Drawing.Pen($darker, 2.0)
            $g.DrawLine($bandPen, 2, 8, 14, 8)
            $bandPen.Dispose()

            # Center button (circle with outline)
            $btnOutline = New-Object System.Drawing.SolidBrush($darker)
            $g.FillEllipse($btnOutline, [float]5.5, [float]5.5, [float]5, [float]5)
            $btnOutline.Dispose()
            $btnCenter = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::White)
            $g.FillEllipse($btnCenter, [float]6.5, [float]6.5, [float]3, [float]3)
            $btnCenter.Dispose()

            # Layer 3: Specular
            $g.FillEllipse($highlightBrush, 4, 3, 5, 3)
        }

        "pacdeluxe" {
            # Pac-Man: circle with wedge mouth cut out
            # Layer 1: Glow
            $g.FillEllipse($glowBrush, 1, 1, 14, 14)

            # Layer 2: Full circle
            $bodyBrush = New-Object System.Drawing.SolidBrush($Color)
            $g.FillEllipse($bodyBrush, 2, 2, 12, 12)
            $bodyBrush.Dispose()

            # Mouth cutout (dark triangle wedge pointing right)
            $mouthPoints = @(
                (New-Object System.Drawing.PointF(8, 8)),       # center
                (New-Object System.Drawing.PointF(15, 4)),      # upper jaw
                (New-Object System.Drawing.PointF(15, 12))      # lower jaw
            )
            $mouthBrush = New-Object System.Drawing.SolidBrush(
                [System.Drawing.Color]::FromArgb(255, 26, 26, 30)
            )
            $g.FillPolygon($mouthBrush, $mouthPoints)
            $mouthBrush.Dispose()

            # Eye dot
            $eyeBrush = New-Object System.Drawing.SolidBrush($darker)
            $g.FillEllipse($eyeBrush, [float]7, [float]4, [float]2.5, [float]2.5)
            $eyeBrush.Dispose()

            # Layer 3: Specular
            $g.FillEllipse($highlightBrush, 4, 3, 4, 3)
        }

        "productivity" {
            # Delegate to category icon (monitor shape)
            $glowBrush.Dispose()
            $highlightBrush.Dispose()
            $g.Dispose()
            $bmp.Dispose()
            return New-CategoryBitmap -Category "Productivity" -Color $Color
        }
    }

    $glowBrush.Dispose()
    $highlightBrush.Dispose()
    $g.Dispose()
    return $bmp
}

function New-ActionBitmap {
    <#
    .SYNOPSIS
    Creates a 16x16 bitmap for an action menu item using filled shapes with depth.
    Uses the three-layer depth system: shadow/glow, main fill, specular highlight.
    .PARAMETER Action
    One of: Restore, Audit, Backups, QuickPanel, Settings, Exit
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
