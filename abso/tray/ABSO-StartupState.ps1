# ABSO-StartupState.ps1 - Startup profile state resolution helpers for A.B.S.O. tray

function Write-StartupStateLog {
    param(
        [string]$Message,
        [string]$Level = "INFO"
    )

    if (Get-Command Write-TrayLog -ErrorAction SilentlyContinue) {
        Write-TrayLog $Message -Level $Level
    }
}

function ConvertTo-StartupTimestamp {
    param([object]$Value)

    if ($null -eq $Value) {
        return $null
    }

    $text = "$Value".Trim()
    if ([string]::IsNullOrWhiteSpace($text)) {
        return $null
    }

    $styles = [System.Globalization.DateTimeStyles]::AssumeLocal
    [datetime]$parsed = [datetime]::MinValue
    if ([datetime]::TryParse($text, [System.Globalization.CultureInfo]::InvariantCulture, $styles, [ref]$parsed)) {
        return $parsed
    }
    if ([datetime]::TryParse($text, [ref]$parsed)) {
        return $parsed
    }

    return $null
}

function New-StartupProfileRecord {
    param(
        [string]$Status,
        [string]$Id = $null,
        [string]$Name = $null,
        [string]$Timestamp = $null,
        [string]$Source = "unknown",
        [string]$Path = $null,
        [int]$SourceRank = 0,
        [string]$TimestampSource = $null
    )

    $parsedAt = ConvertTo-StartupTimestamp -Value $Timestamp

    return [ordered]@{
        status           = if ([string]::IsNullOrWhiteSpace($Status)) { "active" } else { $Status }
        id               = if ([string]::IsNullOrWhiteSpace($Id)) { $null } else { $Id }
        name             = if ([string]::IsNullOrWhiteSpace($Name)) { $null } else { $Name }
        timestamp        = if ([string]::IsNullOrWhiteSpace($Timestamp)) { $null } else { $Timestamp }
        parsed_at        = $parsedAt
        has_timestamp    = ($null -ne $parsedAt)
        source           = $Source
        path             = if ([string]::IsNullOrWhiteSpace($Path)) { $null } else { $Path }
        source_rank      = $SourceRank
        timestamp_source = if ([string]::IsNullOrWhiteSpace($TimestampSource)) { $null } else { $TimestampSource }
        decision         = $null
        candidate_count  = 0
    }
}

function Format-StartupProfileRecord {
    param([object]$Record)

    if (-not $Record) {
        return "null"
    }

    $status = if ($Record.status) { "$($Record.status)" } else { "unknown" }
    $idPart = if ($Record.id) { "$($Record.id)" } else { "<none>" }
    $tsPart = if ($Record.timestamp) { "$($Record.timestamp)" } else { "<no-timestamp>" }
    $srcPart = if ($Record.source) { "$($Record.source)" } else { "unknown" }
    $pathPart = if ($Record.path) { " path=$($Record.path)" } else { "" }
    $timeSrcPart = if ($Record.timestamp_source) { " ts_source=$($Record.timestamp_source)" } else { "" }

    return "$srcPart [$status] $idPart @ $tsPart$timeSrcPart$pathPart"
}

function Read-ActiveProfileFromStateFile {
    param(
        [string]$StatePath,
        [hashtable]$ProfileMap = $null
    )

    if ([string]::IsNullOrWhiteSpace($StatePath) -or -not (Test-Path $StatePath)) {
        return $null
    }

    try {
        $raw = Get-Content -Path $StatePath -Raw -ErrorAction Stop
        if ([string]::IsNullOrWhiteSpace($raw)) { return $null }

        $state = $raw | ConvertFrom-Json
        if (-not $state) { return $null }

        $profileId = if ($state.current_profile) { "$($state.current_profile)" } else { $null }
        if ([string]::IsNullOrWhiteSpace($profileId)) { return $null }

        $profileName = $null
        if ($ProfileMap -and $ProfileMap.Contains($profileId) -and $ProfileMap[$profileId].Name) {
            $profileName = "$($ProfileMap[$profileId].Name)"
        }

        $timestamp = $null
        $timestampSource = $null
        if ($state.applied_at) {
            $timestamp = "$($state.applied_at)"
            $timestampSource = "state.applied_at"
        }
        else {
            try {
                $timestamp = (Get-Item -LiteralPath $StatePath -ErrorAction Stop).LastWriteTime.ToString("o")
                $timestampSource = "file_mtime"
            }
            catch {}
        }

        return New-StartupProfileRecord `
            -Status "active" `
            -Id $profileId `
            -Name $profileName `
            -Timestamp $timestamp `
            -Source "state_file" `
            -Path $StatePath `
            -SourceRank 20 `
            -TimestampSource $timestampSource
    }
    catch {
        Write-StartupStateLog "Failed reading profile state file '$StatePath': $($_.Exception.Message)" "WARN"
        return $null
    }
}

function Resolve-StartupActiveProfile {
    param(
        [object]$Config,
        [string[]]$StateCandidates = $null,
        [hashtable]$ProfileMap = $null
    )

    $profiles = if ($ProfileMap) { $ProfileMap } elseif ($script:Profiles) { $script:Profiles } else { [ordered]@{} }
    $candidates = @()

    $resolvedStateCandidates = @()
    if ($StateCandidates -and $StateCandidates.Count -gt 0) {
        $resolvedStateCandidates = @($StateCandidates)
    }
    else {
        if ($script:ProjectRoot) {
            $resolvedStateCandidates += Join-Path $script:ProjectRoot ".abso_state.json"
        }

        try {
            $localDataRoot = Join-Path ([Environment]::GetFolderPath("LocalApplicationData")) "AdaptiveBattleStationOptimizer"
            if ($localDataRoot) {
                $resolvedStateCandidates += Join-Path $localDataRoot ".abso_state.json"
            }
        }
        catch {}
    }

    $uniqueStateCandidates = @()
    foreach ($candidate in @($resolvedStateCandidates)) {
        if ([string]::IsNullOrWhiteSpace("$candidate")) { continue }
        if ($uniqueStateCandidates -contains $candidate) { continue }
        $uniqueStateCandidates += $candidate
    }

    foreach ($statePath in $uniqueStateCandidates) {
        $record = Read-ActiveProfileFromStateFile -StatePath $statePath -ProfileMap $profiles
        if (-not $record) { continue }

        if (-not $profiles.Contains($record.id)) {
            Write-StartupStateLog "State file '$statePath' references unknown profile '$($record.id)'; skipping candidate" "WARN"
            continue
        }

        $candidates += $record
    }

    if ($Config -and $null -ne $Config.lastProfileState) {
        $state = $Config.lastProfileState
        $status = if ($state.status) { "$($state.status)".ToLowerInvariant() } else { "active" }
        if ($status -ne "active" -and $status -ne "restored") {
            $status = "active"
        }

        $candidateId = if ($status -eq "active" -and $state.id) { "$($state.id)" } else { $null }
        if ($status -eq "active" -and -not [string]::IsNullOrWhiteSpace($candidateId) -and -not $profiles.Contains($candidateId)) {
            Write-StartupStateLog "Config lastProfileState references unknown profile '$candidateId'; skipping candidate" "WARN"
        }
        else {
            $candidateName = if ($status -eq "active" -and $state.name) {
                "$($state.name)"
            }
            elseif ($status -eq "active" -and $candidateId -and $profiles.Contains($candidateId) -and $profiles[$candidateId].Name) {
                "$($profiles[$candidateId].Name)"
            }
            else {
                $null
            }
            $timestamp = if ($state.timestamp) { "$($state.timestamp)" } else { $null }
            $source = if ($state.source) { "last_profile_state:$($state.source)" } else { "last_profile_state" }
            $candidates += New-StartupProfileRecord `
                -Status $status `
                -Id $candidateId `
                -Name $candidateName `
                -Timestamp $timestamp `
                -Source $source `
                -SourceRank 30 `
                -TimestampSource "config.lastProfileState.timestamp"
        }
    }

    if ($Config -and $Config.recentProfiles -and $Config.recentProfiles.Count -gt 0) {
        $lastEntry = $Config.recentProfiles[0]
        $lastId = if ($lastEntry.id) { "$($lastEntry.id)" } else { $null }
        if (-not [string]::IsNullOrWhiteSpace($lastId) -and $profiles.Contains($lastId)) {
            $timestamp = if ($lastEntry.recorded_at) { "$($lastEntry.recorded_at)" } elseif ($lastEntry.timestamp) { "$($lastEntry.timestamp)" } else { $null }
            $timestampSource = if ($lastEntry.recorded_at) { "recentProfiles.recorded_at" } elseif ($lastEntry.timestamp) { "recentProfiles.timestamp" } else { $null }
            $candidates += New-StartupProfileRecord `
                -Status "active" `
                -Id $lastId `
                -Name $(if ($lastEntry.name) { "$($lastEntry.name)" } else { "$($profiles[$lastId].Name)" }) `
                -Timestamp $timestamp `
                -Source "recent_history" `
                -SourceRank 10 `
                -TimestampSource $timestampSource
        }
    }

    if ($candidates.Count -eq 0) {
        return [ordered]@{
            status          = "none"
            id              = $null
            name            = $null
            timestamp       = $null
            source          = "none"
            path            = $null
            decision        = "no_candidate"
            candidate_count = 0
        }
    }

    $orderedCandidates = @(
        $candidates | Sort-Object `
            @{ Expression = { if ($_.has_timestamp) { 1 } else { 0 } }; Descending = $true }, `
            @{ Expression = { if ($_.parsed_at) { $_.parsed_at.Ticks } else { 0 } }; Descending = $true }, `
            @{ Expression = { $_.source_rank }; Descending = $true }
    )

    $summary = @($orderedCandidates | ForEach-Object { Format-StartupProfileRecord -Record $_ }) -join "; "
    Write-StartupStateLog "Startup restore candidates: $summary"

    $selected = $orderedCandidates[0]
    $selected.decision = if ($orderedCandidates.Count -gt 1) { "newest_timestamp" } else { "single_candidate" }
    $selected.candidate_count = $orderedCandidates.Count

    if ($orderedCandidates.Count -gt 1) {
        $firstMeaning = if ($selected.status -eq "active") { "active:$($selected.id)" } else { $selected.status }
        $second = $orderedCandidates[1]
        $secondMeaning = if ($second.status -eq "active") { "active:$($second.id)" } else { $second.status }
        if ($firstMeaning -ne $secondMeaning) {
            $selected.decision = "resolved_conflict_by_timestamp"
            Write-StartupStateLog "Startup restore conflict detected; selected $(Format-StartupProfileRecord -Record $selected)" "WARN"
        }
    }

    return [ordered]@{
        status          = $selected.status
        id              = $selected.id
        name            = $selected.name
        timestamp       = $selected.timestamp
        source          = $selected.source
        path            = $selected.path
        decision        = $selected.decision
        candidate_count = $selected.candidate_count
    }
}
