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

function Get-CanonicalStartupSource {
    param(
        [object]$Source,
        [string]$Default = "unknown"
    )

    if ($null -eq $Source) {
        return $Default
    }

    $text = "$Source".Trim()
    if ([string]::IsNullOrWhiteSpace($text)) {
        return $Default
    }

    # Startup restore used to persist sources such as
    # startup_restore:last_profile_state:startup_restore:state_file on every
    # tray launch. Strip wrapper prefixes so logs and tray config stay bounded.
    $wrapperPattern = '^(startup_restore|last_profile_state):(.+)$'
    while ($text -match $wrapperPattern) {
        $text = "$($Matches[2])".Trim()
        if ([string]::IsNullOrWhiteSpace($text)) {
            return $Default
        }
    }

    return $text
}

function Get-LastProfileStateCandidateSource {
    param([object]$Source)

    $baseSource = Get-CanonicalStartupSource -Source $Source -Default "unknown"
    if ($baseSource -eq "unknown") {
        return "last_profile_state"
    }

    return "last_profile_state:$baseSource"
}

function Get-StartupRestoreStateSource {
    param([object]$Source)

    $baseSource = Get-CanonicalStartupSource -Source $Source -Default "startup_restore"
    if ($baseSource -eq "startup_restore") {
        return "startup_restore"
    }

    return "startup_restore:$baseSource"
}

function Get-StartupProfileMeaning {
    param([object]$Record)

    if (-not $Record) {
        return "none"
    }

    if ("$($Record.status)".ToLowerInvariant() -eq "restored") {
        return "restored"
    }

    if ($Record.id) {
        return "active:$($Record.id)"
    }

    return "active:<none>"
}

function Select-CorroboratedTrayCandidate {
    param([object[]]$Candidates)

    if (-not $Candidates -or $Candidates.Count -eq 0) {
        return $null
    }

    $lastProfileState = @(
        $Candidates | Where-Object { "$($_.source)" -like "last_profile_state:*" }
    ) | Select-Object -First 1
    $recentHistory = @(
        $Candidates | Where-Object { "$($_.source)" -eq "recent_history" }
    ) | Select-Object -First 1

    if (-not $lastProfileState -or -not $recentHistory) {
        return $null
    }

    $lastMeaning = Get-StartupProfileMeaning -Record $lastProfileState
    $recentMeaning = Get-StartupProfileMeaning -Record $recentHistory
    if ($lastMeaning -ne $recentMeaning) {
        return $null
    }

    return $lastProfileState
}

function Select-CorroboratedStateFileCandidate {
    param([object[]]$Candidates)

    if (-not $Candidates -or $Candidates.Count -eq 0) {
        return $null
    }

    $stateFiles = @(
        $Candidates | Where-Object { "$($_.source)" -eq "state_file" }
    )
    if ($stateFiles.Count -lt 2) {
        return $null
    }

    $groups = @{}
    foreach ($record in $stateFiles) {
        $meaning = Get-StartupProfileMeaning -Record $record
        if (-not $groups.ContainsKey($meaning)) {
            $groups[$meaning] = @()
        }
        $groups[$meaning] += $record
    }

    $corroborated = @()
    foreach ($meaning in $groups.Keys) {
        $records = @($groups[$meaning])
        if ($records.Count -lt 2) { continue }
        $corroborated += @(
            $records | Sort-Object `
                @{ Expression = { if ($_.has_timestamp) { 1 } else { 0 } }; Descending = $true }, `
                @{ Expression = { if ($_.parsed_at) { $_.parsed_at.Ticks } else { 0 } }; Descending = $true } |
                Select-Object -First 1
        )
    }

    if ($corroborated.Count -eq 0) {
        return $null
    }

    return @(
        $corroborated | Sort-Object `
            @{ Expression = { if ($_.has_timestamp) { 1 } else { 0 } }; Descending = $true }, `
            @{ Expression = { if ($_.parsed_at) { $_.parsed_at.Ticks } else { 0 } }; Descending = $true }
    ) | Select-Object -First 1
}

function Repair-StartupActiveProfileState {
    param([object]$Record)

    if (-not $Record) { return $false }
    if ("$($Record.status)".ToLowerInvariant() -ne "active") { return $false }
    if ([string]::IsNullOrWhiteSpace("$($Record.id)")) { return $false }
    if ([string]::IsNullOrWhiteSpace("$($Record.sync_state_path)")) { return $false }

    $statePath = "$($Record.sync_state_path)"
    $appliedAt = if ($Record.timestamp) { "$($Record.timestamp)" } else { (Get-Date).ToString("o") }

    $state = @{
        current_profile = "$($Record.id)"
        applied_at = $appliedAt
        reboot_pending = $false
        reboot_reasons = @()
        source = "tray_startup_reconciliation"
    }

    try {
        $parent = Split-Path -Parent $statePath
        if (-not [string]::IsNullOrWhiteSpace($parent) -and -not (Test-Path $parent)) {
            New-Item -Path $parent -ItemType Directory -Force -ErrorAction Stop | Out-Null
        }

        $tmpPath = "$statePath.tmp"
        $jsonText = ($state | ConvertTo-Json -Depth 6) + [Environment]::NewLine
        [System.IO.File]::WriteAllText($tmpPath, $jsonText, [System.Text.UTF8Encoding]::new($false))
        Move-Item -LiteralPath $tmpPath -Destination $statePath -Force -ErrorAction Stop
        Write-StartupStateLog "Reconciled active profile state file '$statePath' to '$($Record.id)' using corroborated tray state"
        return $true
    }
    catch {
        Write-StartupStateLog "Failed reconciling active profile state file '$statePath': $($_.Exception.Message)" "WARN"
        return $false
    }
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

        # Normalize retired ids via the alias map so state written before a
        # profile consolidation still resolves to a live profile.
        if (Get-Command -Name Resolve-ProfileAlias -ErrorAction SilentlyContinue) {
            $canonical = Resolve-ProfileAlias $profileId
            if ($canonical -and $canonical -ne $profileId) {
                Write-StartupStateLog "State file '$StatePath' profile id '$profileId' aliased to '$canonical'"
                $profileId = $canonical
            }
        }

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
    if ($PSBoundParameters.ContainsKey("StateCandidates")) {
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
        if ($candidateId -and (Get-Command -Name Resolve-ProfileAlias -ErrorAction SilentlyContinue)) {
            $canonicalCandidate = Resolve-ProfileAlias $candidateId
            if ($canonicalCandidate -and $canonicalCandidate -ne $candidateId) {
                Write-StartupStateLog "Config lastProfileState id '$candidateId' aliased to '$canonicalCandidate'"
                $candidateId = $canonicalCandidate
            }
        }
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
            $source = Get-LastProfileStateCandidateSource -Source $state.source
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

    $corroboratedTrayCandidate = Select-CorroboratedTrayCandidate -Candidates $candidates
    if ($corroboratedTrayCandidate) {
        $corroboratedMeaning = Get-StartupProfileMeaning -Record $corroboratedTrayCandidate
        $corroboratedStateFileCandidate = Select-CorroboratedStateFileCandidate -Candidates $candidates
        if ($corroboratedStateFileCandidate) {
            $stateFileMeaning = Get-StartupProfileMeaning -Record $corroboratedStateFileCandidate
            if ($stateFileMeaning -ne $corroboratedMeaning) {
                $stateTicks = if ($corroboratedStateFileCandidate.parsed_at) {
                    $corroboratedStateFileCandidate.parsed_at.Ticks
                }
                else {
                    0
                }
                $trayTicks = if ($corroboratedTrayCandidate.parsed_at) {
                    $corroboratedTrayCandidate.parsed_at.Ticks
                }
                else {
                    0
                }

                if ($stateTicks -gt $trayTicks) {
                    Write-StartupStateLog (
                        "Using corroborated newer state-file candidate '" +
                        (Format-StartupProfileRecord -Record $corroboratedStateFileCandidate) +
                        "' over older tray state '" +
                        (Format-StartupProfileRecord -Record $corroboratedTrayCandidate) +
                        "'"
                    ) "WARN"

                    $corroboratedStateFileCandidate.decision = "corroborated_state_files_newer"
                    $corroboratedStateFileCandidate.candidate_count = $candidates.Count

                    return [ordered]@{
                        status          = $corroboratedStateFileCandidate.status
                        id              = $corroboratedStateFileCandidate.id
                        name            = $corroboratedStateFileCandidate.name
                        timestamp       = $corroboratedStateFileCandidate.timestamp
                        source          = $corroboratedStateFileCandidate.source
                        path            = $corroboratedStateFileCandidate.path
                        sync_state_path = $null
                        decision        = $corroboratedStateFileCandidate.decision
                        candidate_count = $corroboratedStateFileCandidate.candidate_count
                    }
                }
            }
        }

        $conflictingStateFile = @(
            $candidates |
                Where-Object {
                    "$($_.source)" -eq "state_file" -and
                    (Get-StartupProfileMeaning -Record $_) -ne $corroboratedMeaning
                }
        ) | Sort-Object `
            @{ Expression = { if ($_.has_timestamp) { 1 } else { 0 } }; Descending = $true }, `
            @{ Expression = { if ($_.parsed_at) { $_.parsed_at.Ticks } else { 0 } }; Descending = $true } |
            Select-Object -First 1

        if ($conflictingStateFile) {
            $stateTicks = if ($conflictingStateFile.parsed_at) {
                $conflictingStateFile.parsed_at.Ticks
            }
            else {
                0
            }
            $trayTicks = if ($corroboratedTrayCandidate.parsed_at) {
                $corroboratedTrayCandidate.parsed_at.Ticks
            }
            else {
                0
            }

            if ($stateTicks -gt $trayTicks) {
                Write-StartupStateLog (
                    "Using newer state-file candidate '" +
                    (Format-StartupProfileRecord -Record $conflictingStateFile) +
                    "' over older corroborated tray state '" +
                    (Format-StartupProfileRecord -Record $corroboratedTrayCandidate) +
                    "'"
                ) "WARN"

                $conflictingStateFile.decision = "newer_state_file"
                $conflictingStateFile.candidate_count = $candidates.Count

                return [ordered]@{
                    status          = $conflictingStateFile.status
                    id              = $conflictingStateFile.id
                    name            = $conflictingStateFile.name
                    timestamp       = $conflictingStateFile.timestamp
                    source          = $conflictingStateFile.source
                    path            = $conflictingStateFile.path
                    sync_state_path = $null
                    decision        = $conflictingStateFile.decision
                    candidate_count = $conflictingStateFile.candidate_count
                }
            }

            Write-StartupStateLog (
                "Ignoring uncorroborated state-file candidate '" +
                (Format-StartupProfileRecord -Record $conflictingStateFile) +
                "' in favor of corroborated tray state '" +
                (Format-StartupProfileRecord -Record $corroboratedTrayCandidate) +
                "'"
            ) "WARN"

            $corroboratedTrayCandidate.decision = "corroborated_tray_state"
            $corroboratedTrayCandidate.candidate_count = $candidates.Count

            return [ordered]@{
                status          = $corroboratedTrayCandidate.status
                id              = $corroboratedTrayCandidate.id
                name            = $corroboratedTrayCandidate.name
                timestamp       = $corroboratedTrayCandidate.timestamp
                source          = $corroboratedTrayCandidate.source
                path            = $corroboratedTrayCandidate.path
                sync_state_path = $conflictingStateFile.path
                decision        = $corroboratedTrayCandidate.decision
                candidate_count = $corroboratedTrayCandidate.candidate_count
            }
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
        sync_state_path = $null
        decision        = $selected.decision
        candidate_count = $selected.candidate_count
    }
}
