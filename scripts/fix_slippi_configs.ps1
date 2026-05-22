# Fix Slippi Dolphin configs for ABSO's no-sync Slippi baseline
# Run this before launching Slippi if the launcher has overwritten settings

$ErrorActionPreference = "Stop"

$slippiBase = "$env:APPDATA\Slippi Launcher\netplay\User\Config"
$gfxIni = Join-Path $slippiBase "GFX.ini"
$dolphinIni = Join-Path $slippiBase "Dolphin.ini"

Write-Host "=== Slippi Config Fixer ===" -ForegroundColor Cyan

# GFX.ini fixes
if (Test-Path $gfxIni) {
    $gfx = Get-Content $gfxIni -Raw
    $changed = $false

    # EFBScale = 1 (Native resolution)
    if ($gfx -match "EFBScale = 2") {
        $gfx = $gfx -replace "EFBScale = 2", "EFBScale = 1"
        Write-Host "[FIX] EFBScale: 2 -> 1" -ForegroundColor Yellow
        $changed = $true
    }

    # TextureScalingFactor = 1
    if ($gfx -match "TextureScalingFactor = 2") {
        $gfx = $gfx -replace "TextureScalingFactor = 2", "TextureScalingFactor = 1"
        Write-Host "[FIX] TextureScalingFactor: 2 -> 1" -ForegroundColor Yellow
        $changed = $true
    }

    # UseScalingFilter = False
    if ($gfx -match "UseScalingFilter = True") {
        $gfx = $gfx -replace "UseScalingFilter = True", "UseScalingFilter = False"
        Write-Host "[FIX] UseScalingFilter: True -> False" -ForegroundColor Yellow
        $changed = $true
    }

    # UseDePosterize = False
    if ($gfx -match "UseDePosterize = True") {
        $gfx = $gfx -replace "UseDePosterize = True", "UseDePosterize = False"
        Write-Host "[FIX] UseDePosterize: True -> False" -ForegroundColor Yellow
        $changed = $true
    }

    if ($changed) {
        Set-Content $gfxIni $gfx -NoNewline
        Write-Host "[OK] GFX.ini updated" -ForegroundColor Green
    } else {
        Write-Host "[OK] GFX.ini already at ABSO target" -ForegroundColor Green
    }
} else {
    Write-Host "[WARN] GFX.ini not found" -ForegroundColor Red
}

# Dolphin.ini fixes
if (Test-Path $dolphinIni) {
    $dolphin = Get-Content $dolphinIni -Raw
    $changed = $false

    # ReduceTimingDispersion = True (Ishiiruka-specific)
    if ($dolphin -match "ReduceTimingDispersion = False") {
        $dolphin = $dolphin -replace "ReduceTimingDispersion = False", "ReduceTimingDispersion = True"
        Write-Host "[FIX] ReduceTimingDispersion: False -> True" -ForegroundColor Yellow
        $changed = $true
    }

    if ($changed) {
        Set-Content $dolphinIni $dolphin -NoNewline
        Write-Host "[OK] Dolphin.ini updated" -ForegroundColor Green
    } else {
        Write-Host "[OK] Dolphin.ini already at ABSO target" -ForegroundColor Green
    }
} else {
    Write-Host "[WARN] Dolphin.ini not found" -ForegroundColor Red
}

Write-Host "`n=== Done ===" -ForegroundColor Cyan
Write-Host "Slippi configs now match ABSO's no-sync Slippi baseline."
