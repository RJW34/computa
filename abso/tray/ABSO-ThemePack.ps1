# ABSO-ThemePack.ps1 - Selectable icon/sound theme packs for the A.B.S.O. tray
#
# A theme is a folder under abso/tray/themes/<name>/ containing a theme.json
# manifest plus any icon (.ico) and sound (.mp3/.wav) assets it references.
# The active theme is chosen by the `theme` key in tray-config.json
# (%APPDATA%\ABSO\tray-config.json); changing it takes effect on tray restart.
#
# Manifest contract (all keys optional — anything missing falls back to the
# built-in defaults: generated GDI+ icons and Windows system sound cues):
#
#   icons.idle / active / gaming / applying / warning / error
#       Filename relative to the theme folder, or null for the generated icon.
#   icons.applySequence
#       Array of filenames played as the apply-success animation frames.
#       Empty/missing means no file-based animation (state icons still swap).
#   sounds.success / fail / vrrWarning / restart
#       Filename relative to the theme folder, "system:<Name>" for a Windows
#       system sound (Asterisk, Beep, Exclamation, Hand, Question), or "none"
#       to silence that cue.
#
# See themes/README.md for a walkthrough and themes/default/theme.json for a
# copyable starting point.

$script:ThemePackCache = @{}

# Built-in cue fallbacks used when a theme omits a sound (or the referenced
# file is missing). Friends always get audible feedback out of the box without
# any bundled media files.
$script:ThemeDefaultSoundCues = @{
    success    = "system:Asterisk"
    fail       = "system:Hand"
    vrrWarning = "system:Exclamation"
    restart    = "system:Asterisk"
}

function Get-ThemesRootPath {
    return (Join-Path $PSScriptRoot "themes")
}

function Get-ActiveThemeName {
    <#
    .SYNOPSIS
    Returns the configured theme name, defaulting to "default".
    #>
    try {
        if ($script:TrayConfig -and $script:TrayConfig.ContainsKey("theme")) {
            $name = "$($script:TrayConfig.theme)".Trim()
            if (-not [string]::IsNullOrWhiteSpace($name)) {
                # Theme names are folder names; refuse path separators outright.
                if ($name -notmatch '[\\/]' -and $name -ne "." -and $name -ne "..") {
                    return $name
                }
            }
        }
    }
    catch {}
    return "default"
}

function Get-ThemeManifest {
    <#
    .SYNOPSIS
    Loads (and caches) the active theme's manifest. Returns $null when the
    theme folder or manifest is absent/corrupt — callers treat $null as
    "use built-in defaults".
    #>
    param([string]$ThemeName = $null)

    $name = if ([string]::IsNullOrWhiteSpace($ThemeName)) { Get-ActiveThemeName } else { $ThemeName }

    if ($script:ThemePackCache.ContainsKey($name)) {
        return $script:ThemePackCache[$name]
    }

    $manifest = $null
    try {
        $themeDir = Join-Path (Get-ThemesRootPath) $name
        $manifestPath = Join-Path $themeDir "theme.json"
        if (Test-Path $manifestPath) {
            $raw = Get-Content -Path $manifestPath -Raw -ErrorAction Stop
            if (-not [string]::IsNullOrWhiteSpace($raw)) {
                $parsed = $raw | ConvertFrom-Json
                $manifest = @{
                    Name    = $name
                    Dir     = $themeDir
                    Icons   = $parsed.icons
                    Sounds  = $parsed.sounds
                }
            }
        }
    }
    catch {
        if (Get-Command Write-TrayLog -ErrorAction SilentlyContinue) {
            Write-TrayLog "Theme '$name' manifest unreadable: $($_.Exception.Message) - using built-in defaults" -Level "WARN"
        }
        $manifest = $null
    }

    $script:ThemePackCache[$name] = $manifest
    return $manifest
}

function Get-ThemeIconPath {
    <#
    .SYNOPSIS
    Returns the absolute path of the themed icon for a state, or $null when
    the theme provides none (caller falls back to the generated icon).
    .PARAMETER State
    One of: Idle, Active, Gaming, Applying, Warning, Error
    #>
    param([string]$State)

    $manifest = Get-ThemeManifest
    if (-not $manifest -or -not $manifest.Icons) { return $null }

    $key = "$State"
    $key = $key.Substring(0, 1).ToLowerInvariant() + $key.Substring(1)
    $entry = $manifest.Icons.$key
    if ([string]::IsNullOrWhiteSpace("$entry")) { return $null }

    $path = Join-Path $manifest.Dir "$entry"
    if (Test-Path $path) { return $path }

    if (Get-Command Write-TrayLog -ErrorAction SilentlyContinue) {
        Write-TrayLog "Theme icon missing for state '$State': $path - using generated icon" -Level "WARN"
    }
    return $null
}

function Get-ThemeApplySequencePaths {
    <#
    .SYNOPSIS
    Returns existing absolute paths for the apply-success animation frames.
    Empty array when the theme defines none.
    #>
    $manifest = Get-ThemeManifest
    if (-not $manifest -or -not $manifest.Icons) { return @() }

    $sequence = @($manifest.Icons.applySequence) | Where-Object { -not [string]::IsNullOrWhiteSpace("$_") }
    $paths = @()
    foreach ($entry in $sequence) {
        $path = Join-Path $manifest.Dir "$entry"
        if (Test-Path $path) {
            $paths += $path
        }
    }
    return $paths
}

function Get-ThemeSoundCue {
    <#
    .SYNOPSIS
    Resolves a sound event to a playable cue.
    .PARAMETER SoundEvent
    One of: success, fail, vrrWarning, restart
    .OUTPUTS
    Hashtable: @{ Type = "file"; Path = ... } | @{ Type = "system"; Name = ... } | @{ Type = "none" }
    #>
    param([string]$SoundEvent)

    $fallback = $script:ThemeDefaultSoundCues[$SoundEvent]
    $manifest = Get-ThemeManifest

    $entry = $null
    if ($manifest -and $manifest.Sounds) {
        $entry = $manifest.Sounds.$SoundEvent
    }
    if ([string]::IsNullOrWhiteSpace("$entry")) {
        $entry = $fallback
    }

    $entryText = "$entry".Trim()
    if ($entryText -ieq "none") {
        return @{ Type = "none" }
    }
    if ($entryText -imatch '^system:(.+)$') {
        return @{ Type = "system"; Name = $Matches[1].Trim() }
    }

    if ($manifest) {
        $path = Join-Path $manifest.Dir $entryText
        if (Test-Path $path) {
            return @{ Type = "file"; Path = $path }
        }
        if (Get-Command Write-TrayLog -ErrorAction SilentlyContinue) {
            Write-TrayLog "Theme sound missing for '$SoundEvent': $path - using system cue" -Level "WARN"
        }
    }

    # Manifest absent or file missing: land on the built-in system cue.
    if ("$fallback" -imatch '^system:(.+)$') {
        return @{ Type = "system"; Name = $Matches[1].Trim() }
    }
    return @{ Type = "none" }
}

function Play-SystemSoundCue {
    <#
    .SYNOPSIS
    Plays a named Windows system sound (respects the user's sound scheme).
    #>
    param([string]$Name)

    try {
        switch -Regex ($Name) {
            '^(?i)asterisk$'    { [System.Media.SystemSounds]::Asterisk.Play(); return $true }
            '^(?i)beep$'        { [System.Media.SystemSounds]::Beep.Play(); return $true }
            '^(?i)exclamation$' { [System.Media.SystemSounds]::Exclamation.Play(); return $true }
            '^(?i)hand$'        { [System.Media.SystemSounds]::Hand.Play(); return $true }
            '^(?i)question$'    { [System.Media.SystemSounds]::Question.Play(); return $true }
        }
        [System.Media.SystemSounds]::Asterisk.Play()
        return $true
    }
    catch {
        if (Get-Command Write-TrayLog -ErrorAction SilentlyContinue) {
            Write-TrayLog "Failed to play system sound '$Name': $($_.Exception.Message)" -Level "WARN"
        }
        return $false
    }
}
