$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$outputPath = Join-Path $repoRoot 'state\citadel_status.json'
$absoStatePath = Join-Path $repoRoot '.abso_state.json'
$powerStatePath = Join-Path $repoRoot '.power_switcher_state.json'

function Read-Json([string] $Path) {
    if (-not (Test-Path $Path)) { return $null }
    try { return Get-Content $Path -Raw | ConvertFrom-Json } catch { return $null }
}

function Get-IsoStamp([string] $Path) {
    if (Test-Path $Path) { return (Get-Item $Path).LastWriteTimeUtc.ToString('o') }
    return ''
}

function New-Signal([string] $Name, [string] $Label, [object] $Value, [string] $Status = 'neutral') {
    return [ordered]@{ name = $Name; label = $Label; value = [string] $Value; status = $Status }
}

function New-Artifact([string] $Label, [string] $RelativePath, [string] $Kind = '') {
    $fullPath = Join-Path $repoRoot $RelativePath
    return [ordered]@{ label = $Label; path = $RelativePath; updated_at = Get-IsoStamp $fullPath; kind = $Kind }
}

$now = (Get-Date).ToUniversalTime().ToString('o')
$absoState = Read-Json $absoStatePath
$powerState = Read-Json $powerStatePath
$currentProfile = if ($absoState) { [string] $absoState.current_profile } else { '' }
$appliedAt = if ($absoState -and $absoState.applied_at) { [string] $absoState.applied_at } else { Get-IsoStamp $absoStatePath }
$rebootPending = $false
if ($absoState -and $null -ne $absoState.reboot_pending) {
    $rebootPending = [bool] $absoState.reboot_pending
}
$powerPlan = if ($powerState) { [string] $powerState.game_plan_name } else { '' }

$status = if ($currentProfile) { 'active' } else { 'idle' }
$health = if (-not $currentProfile) {
    'warning'
} elseif ($rebootPending) {
    'warning'
} else {
    'healthy'
}
$headline = if ($currentProfile) {
    "Profile '$currentProfile' is the last stamped computa state."
} else {
    'computa has no stamped active profile yet.'
}

$signals = @(
    (New-Signal 'current_profile' 'Active profile' ($(if ($currentProfile) { $currentProfile } else { 'none' })) $(if ($currentProfile) { 'good' } else { 'warn' })),
    (New-Signal 'reboot_pending' 'Reboot pending' ($(if ($rebootPending) { 'yes' } else { 'no' })) $(if ($rebootPending) { 'warn' } else { 'good' })),
    (New-Signal 'power_plan' 'Power plan' ($(if ($powerPlan) { $powerPlan } else { 'unknown' })) $(if ($powerPlan) { 'good' } else { 'neutral' }))
)

$artifacts = @(
    (New-Artifact 'ABSO state' '.abso_state.json' 'state'),
    (New-Artifact 'Power switcher state' '.power_switcher_state.json' 'state'),
    (New-Artifact 'Quality rubric' 'docs\QUALITY_RUBRIC.md' 'documentation'),
    (New-Artifact 'Remediation roadmap' 'docs\REMEDIATION_ROADMAP.md' 'documentation')
)

$payload = [ordered]@{
    schema_version = 1
    project_id = 'windowsoptimizerabso'
    generated_at = $now
    updated_at = $appliedAt
    status = $status
    health = $health
    headline = $headline
    signals = $signals
    artifacts = $artifacts
    details = [ordered]@{
        current_profile = $currentProfile
        applied_at = $appliedAt
        reboot_pending = $rebootPending
        reboot_reasons = if ($absoState) { @($absoState.reboot_reasons) } else { @() }
        power_switcher = $powerState
    }
}

New-Item -ItemType Directory -Force -Path (Split-Path $outputPath -Parent) | Out-Null
$json = $payload | ConvertTo-Json -Depth 8
Set-Content -Path $outputPath -Value $json -Encoding utf8
$json
