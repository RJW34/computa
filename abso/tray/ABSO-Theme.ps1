# ABSO-Theme.ps1 - shared tray visual design tokens.
#
# Keep this file free of behavior. It exists so the tray menu, notifications,
# quick panel, and settings surfaces agree on the same colors and type scale.

try { Add-Type -AssemblyName System.Drawing -ErrorAction SilentlyContinue } catch {}

function New-TrayThemeColor {
    param(
        [int]$A,
        [int]$R,
        [int]$G,
        [int]$B
    )

    return [System.Drawing.Color]::FromArgb($A, $R, $G, $B)
}

function Get-TrayThemePalette {
    # "Phosphor bench instrument" tokens — shared with the computa GUI so the
    # tray, toasts, quick panel, and desktop app read as one device. Ink
    # surfaces carry a blue-green cast (deep bench, not neutral gray);
    # phosphor teal is the single dominant signal, amber the secondary.
    $palette = @{
        # Ink surface stack.
        Ink000          = New-TrayThemeColor 255 4 15 18
        Ink100          = New-TrayThemeColor 255 7 24 29
        Ink150          = New-TrayThemeColor 255 9 29 35
        Ink200          = New-TrayThemeColor 255 11 35 42
        Ink250          = New-TrayThemeColor 255 13 42 50
        Ink300          = New-TrayThemeColor 255 16 52 60
        Ink400          = New-TrayThemeColor 255 20 66 74
        Ink500          = New-TrayThemeColor 255 25 82 90

        # Text and rules.
        Paper           = New-TrayThemeColor 255 225 244 240
        Mist            = New-TrayThemeColor 255 148 183 182
        Fog             = New-TrayThemeColor 255 95 127 127
        Rule            = New-TrayThemeColor 70 0 245 212
        RuleSoft        = New-TrayThemeColor 255 12 44 49
        RuleStrong      = New-TrayThemeColor 255 26 88 90

        # Brand and status signals.
        Signal          = New-TrayThemeColor 255 0 245 212
        SignalRule      = New-TrayThemeColor 70 0 245 212
        Success         = New-TrayThemeColor 255 61 222 147
        Warning         = New-TrayThemeColor 255 245 184 64
        Danger          = New-TrayThemeColor 255 255 92 120
        Info            = New-TrayThemeColor 255 82 199 244
        Orchid          = New-TrayThemeColor 255 183 156 255

        # Category accents. These should decorate structure, icons, and chips,
        # not replace the primary row text color.
        CategoryDesktop = New-TrayThemeColor 255 0 245 212
        CategoryFighting = New-TrayThemeColor 255 255 110 122
        CategoryShooter = New-TrayThemeColor 255 82 199 244
        CategoryRpg     = New-TrayThemeColor 255 183 156 255
        CategoryOther   = New-TrayThemeColor 255 61 222 147
        CategoryActions = New-TrayThemeColor 255 245 184 64
        CategorySettings = New-TrayThemeColor 255 158 192 192

        # Legacy keys kept so existing callsites inherit the refreshed system.
        Background      = New-TrayThemeColor 255 7 24 29
        BackgroundDark  = New-TrayThemeColor 255 4 15 18
        BackgroundLight = New-TrayThemeColor 255 16 52 60
        Hover           = New-TrayThemeColor 255 20 66 74
        HoverBright     = New-TrayThemeColor 255 25 82 90
        Text            = New-TrayThemeColor 255 225 244 240
        TextDim         = New-TrayThemeColor 255 148 183 182
        TextDisabled    = New-TrayThemeColor 255 95 127 127
        Border          = New-TrayThemeColor 255 26 88 90
        Separator       = New-TrayThemeColor 255 12 44 49
        AccentGold      = New-TrayThemeColor 255 0 245 212
        AccentGreen     = New-TrayThemeColor 255 61 222 147
        AccentBlue      = New-TrayThemeColor 255 82 199 244
        AccentPurple    = New-TrayThemeColor 255 183 156 255
        AccentAmber     = New-TrayThemeColor 255 245 184 64
        AccentRed       = New-TrayThemeColor 255 255 92 120
        AccentTeal      = New-TrayThemeColor 255 64 201 181
        FavoriteStar    = New-TrayThemeColor 255 255 203 84
        CatFighting     = New-TrayThemeColor 255 255 110 122
        CatARPG         = New-TrayThemeColor 255 183 156 255
        CatShooter      = New-TrayThemeColor 255 82 199 244
        CatStreaming    = New-TrayThemeColor 255 64 201 181
        CatOther        = New-TrayThemeColor 255 61 222 147
        CatProd         = New-TrayThemeColor 255 245 184 64
        Lagoon          = New-TrayThemeColor 255 0 245 212
        Moss            = New-TrayThemeColor 255 61 222 147
        Ochre           = New-TrayThemeColor 255 245 184 64
        Coral           = New-TrayThemeColor 255 255 92 120
    }

    return $palette
}

function Get-TrayThemeColor {
    param(
        [string]$Name,
        [AllowNull()][System.Drawing.Color]$Fallback = [System.Drawing.Color]::Empty
    )

    if (-not $script:TrayThemePalette) {
        $script:TrayThemePalette = Get-TrayThemePalette
    }

    if ($script:TrayThemePalette.ContainsKey($Name)) {
        return $script:TrayThemePalette[$Name]
    }

    return $Fallback
}

function New-TrayThemeFont {
    param(
        [string[]]$Families,
        [float]$Size,
        [System.Drawing.FontStyle]$Style = [System.Drawing.FontStyle]::Regular
    )

    foreach ($family in @($Families)) {
        try {
            $font = New-Object System.Drawing.Font($family, $Size, $Style)
            if ($font.FontFamily.Name -ieq $family) { return $font }
            $root = ($family -split ' ')[0]
            if ($font.FontFamily.Name -ilike "$root*") { return $font }
            $font.Dispose()
        }
        catch {}
    }

    return New-Object System.Drawing.Font("Segoe UI", $Size, $Style)
}

function Initialize-TrayTheme {
    $script:TrayThemePalette = Get-TrayThemePalette
    return $script:TrayThemePalette
}

$script:TrayThemePalette = Initialize-TrayTheme
