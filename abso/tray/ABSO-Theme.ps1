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
    $palette = @{
        # Ink surface stack.
        Ink000          = New-TrayThemeColor 255 8 11 17
        Ink100          = New-TrayThemeColor 255 14 18 26
        Ink150          = New-TrayThemeColor 255 17 21 31
        Ink200          = New-TrayThemeColor 255 19 24 36
        Ink250          = New-TrayThemeColor 255 22 28 41
        Ink300          = New-TrayThemeColor 255 27 34 48
        Ink400          = New-TrayThemeColor 255 36 48 71
        Ink500          = New-TrayThemeColor 255 47 59 83

        # Text and rules.
        Paper           = New-TrayThemeColor 255 232 238 246
        Mist            = New-TrayThemeColor 255 150 162 183
        Fog             = New-TrayThemeColor 255 92 104 128
        Rule            = New-TrayThemeColor 70 0 245 212
        RuleSoft        = New-TrayThemeColor 255 26 34 51
        RuleStrong      = New-TrayThemeColor 255 41 54 78

        # Brand and status signals.
        Signal          = New-TrayThemeColor 255 0 245 212
        SignalRule      = New-TrayThemeColor 70 0 245 212
        Success         = New-TrayThemeColor 255 123 227 158
        Warning         = New-TrayThemeColor 255 229 165 71
        Danger          = New-TrayThemeColor 255 255 107 107
        Info            = New-TrayThemeColor 255 111 184 255
        Orchid          = New-TrayThemeColor 255 183 156 255

        # Category accents. These should decorate structure, icons, and chips,
        # not replace the primary row text color.
        CategoryDesktop = New-TrayThemeColor 255 0 245 212
        CategoryFighting = New-TrayThemeColor 255 255 123 123
        CategoryShooter = New-TrayThemeColor 255 111 184 255
        CategoryRpg     = New-TrayThemeColor 255 183 156 255
        CategoryOther   = New-TrayThemeColor 255 123 227 158
        CategoryActions = New-TrayThemeColor 255 229 165 71
        CategorySettings = New-TrayThemeColor 255 166 176 197

        # Legacy keys kept so existing callsites inherit the refreshed system.
        Background      = New-TrayThemeColor 255 14 18 26
        BackgroundDark  = New-TrayThemeColor 255 8 11 17
        BackgroundLight = New-TrayThemeColor 255 27 34 48
        Hover           = New-TrayThemeColor 255 36 48 71
        HoverBright     = New-TrayThemeColor 255 47 59 83
        Text            = New-TrayThemeColor 255 232 238 246
        TextDim         = New-TrayThemeColor 255 150 162 183
        TextDisabled    = New-TrayThemeColor 255 92 104 128
        Border          = New-TrayThemeColor 255 41 54 78
        Separator       = New-TrayThemeColor 255 26 34 51
        AccentGold      = New-TrayThemeColor 255 0 245 212
        AccentGreen     = New-TrayThemeColor 255 123 227 158
        AccentBlue      = New-TrayThemeColor 255 111 184 255
        AccentPurple    = New-TrayThemeColor 255 183 156 255
        AccentAmber     = New-TrayThemeColor 255 229 165 71
        AccentRed       = New-TrayThemeColor 255 255 107 107
        AccentTeal      = New-TrayThemeColor 255 63 184 171
        FavoriteStar    = New-TrayThemeColor 255 229 165 71
        CatFighting     = New-TrayThemeColor 255 255 123 123
        CatARPG         = New-TrayThemeColor 255 183 156 255
        CatShooter      = New-TrayThemeColor 255 111 184 255
        CatStreaming    = New-TrayThemeColor 255 77 216 201
        CatOther        = New-TrayThemeColor 255 123 227 158
        CatProd         = New-TrayThemeColor 255 229 165 71
        Lagoon          = New-TrayThemeColor 255 0 245 212
        Moss            = New-TrayThemeColor 255 123 227 158
        Ochre           = New-TrayThemeColor 255 229 165 71
        Coral           = New-TrayThemeColor 255 255 107 107
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
