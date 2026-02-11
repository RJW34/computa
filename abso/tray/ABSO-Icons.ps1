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
    Loads an ICO file and returns a detached 16x16 icon clone.
    #>
    param([string]$Path)

    if (-not $Path -or -not (Test-Path $Path)) {
        return $null
    }

    $img = $null
    $bmp = $null
    $hIcon = [IntPtr]::Zero
    try {
        $img = [System.Drawing.Image]::FromFile($Path)
        $bmp = New-Object System.Drawing.Bitmap($img, 16, 16)
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
    .PARAMETER Category
    One of: Fighting, ARPG, Shooter, Productivity, Other
    #>
    param([string]$Category)

    $bmp = New-Object System.Drawing.Bitmap(16, 16)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $g.Clear([System.Drawing.Color]::Transparent)

    $pen = New-Object System.Drawing.Pen([System.Drawing.Color]::White, 1.2)
    $pen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
    $pen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round

    switch ($Category) {
        "Fighting" {
            # Crossed swords
            $g.DrawLine($pen, 3, 12, 13, 2)
            $g.DrawLine($pen, 13, 12, 3, 2)
            $g.DrawLine($pen, 2, 13, 5, 10)
            $g.DrawLine($pen, 11, 10, 14, 13)
        }
        "ARPG" {
            # Shield shape
            $points = @(
                (New-Object System.Drawing.PointF(8, 2)),
                (New-Object System.Drawing.PointF(13, 4)),
                (New-Object System.Drawing.PointF(12, 10)),
                (New-Object System.Drawing.PointF(8, 14)),
                (New-Object System.Drawing.PointF(4, 10)),
                (New-Object System.Drawing.PointF(3, 4))
            )
            $g.DrawPolygon($pen, $points)
        }
        "Shooter" {
            # Crosshair
            $g.DrawEllipse($pen, 4, 4, 8, 8)
            $g.DrawLine($pen, 8, 1, 8, 5)
            $g.DrawLine($pen, 8, 11, 8, 15)
            $g.DrawLine($pen, 1, 8, 5, 8)
            $g.DrawLine($pen, 11, 8, 15, 8)
        }
        "Productivity" {
            # Monitor
            $g.DrawRectangle($pen, 2, 2, 12, 8)
            $g.DrawLine($pen, 8, 10, 8, 13)
            $g.DrawLine($pen, 5, 13, 11, 13)
        }
        default {
            # Star
            $g.DrawLine($pen, 8, 2, 8, 14)
            $g.DrawLine($pen, 2, 8, 14, 8)
            $g.DrawLine($pen, 4, 4, 12, 12)
            $g.DrawLine($pen, 12, 4, 4, 12)
        }
    }

    $pen.Dispose()
    $g.Dispose()

    $hIcon = $bmp.GetHicon()
    $tempIcon = [System.Drawing.Icon]::FromHandle($hIcon)
    $icon = $tempIcon.Clone()
    $tempIcon.Dispose()
    [IconHelper]::DestroyIcon($hIcon) | Out-Null
    $bmp.Dispose()
    return $icon
}
