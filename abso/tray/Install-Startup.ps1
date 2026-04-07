# Install-Startup.ps1 - Add/Remove A.B.S.O. tray from Windows startup
# Usage:
#   .\Install-Startup.ps1 -Install         # Add to startup (Task Scheduler first, shortcut fallback)
#   .\Install-Startup.ps1 -Uninstall       # Remove startup registration
#   .\Install-Startup.ps1 -Status          # Check if installed
#   .\Install-Startup.ps1 -Status -Json    # Machine-readable status

param(
    [switch]$Install,
    [switch]$Uninstall,
    [switch]$Status,
    [switch]$Json
)

$StartupFolder = [Environment]::GetFolderPath("Startup")
$ShortcutPath = Join-Path $StartupFolder "ABSO-Tray.lnk"
$VBSPath = Join-Path $PSScriptRoot "ABSO-Tray.vbs"
$StartupLauncherPath = Join-Path $PSScriptRoot "ABSO-StartupLaunch.ps1"
$TaskName = "ABSO-Tray-Startup"
$TaskDescription = "Start A.B.S.O. tray at user logon with highest privileges"
$CurrentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

function Test-IsAdministrator {
    try {
        $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
        $principal = [Security.Principal.WindowsPrincipal]::new($identity)
        return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    }
    catch {
        return $false
    }
}

function Write-JsonResult {
    param($Obj)
    Write-Output ($Obj | ConvertTo-Json -Depth 5 -Compress)
}

function Invoke-ElevatedSelf {
    param([string[]]$ForwardArgs)

    $elevatedArgs = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", $PSCommandPath
    ) + $ForwardArgs

    $stdoutPath = $null
    $stderrPath = $null
    try {
        if ($Json) {
            $stdoutPath = [System.IO.Path]::GetTempFileName()
            $stderrPath = "$stdoutPath.err"
            $proc = Start-Process -FilePath "powershell.exe" -ArgumentList $elevatedArgs -Verb RunAs -Wait -PassThru `
                -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
            if (Test-Path $stdoutPath) {
                Get-Content -Path $stdoutPath -Raw -ErrorAction SilentlyContinue
            }
            if ($proc.ExitCode -ne 0 -and (Test-Path $stderrPath)) {
                $stderr = Get-Content -Path $stderrPath -Raw -ErrorAction SilentlyContinue
                if (-not [string]::IsNullOrWhiteSpace($stderr)) {
                    Write-Error $stderr.Trim()
                }
            }
            exit $proc.ExitCode
        }

        $proc = Start-Process -FilePath "powershell.exe" -ArgumentList $elevatedArgs -Verb RunAs -Wait -PassThru
        exit $proc.ExitCode
    }
    catch {
        $message = "Administrator privileges are required to update A.B.S.O. startup registration. $($_.Exception.Message)"
        if ($Json) {
            Write-JsonResult ([ordered]@{
                success = $false
                mode = "none"
                message = ""
                warning = $null
                error = $message
                status = $null
            })
        }
        else {
            Write-Host $message -ForegroundColor Red
        }
        exit 1
    }
    finally {
        if ($stdoutPath -and (Test-Path $stdoutPath)) {
            Remove-Item $stdoutPath -Force -ErrorAction SilentlyContinue
        }
        if ($stderrPath -and (Test-Path $stderrPath)) {
            Remove-Item $stderrPath -Force -ErrorAction SilentlyContinue
        }
    }
}

function Test-StartupTaskInstalled {
    try {
        $null = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
        return $true
    }
    catch {
        return $false
    }
}

function Get-StartupTaskInfoSafe {
    try {
        $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
        $taskInfo = Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction SilentlyContinue
        $runLevelRaw = $task.Principal.RunLevel
        $runLevelValue = if ($null -eq $runLevelRaw) { "" } else { "$runLevelRaw" }
        $taskHighest = $false
        if ($runLevelRaw -is [int]) {
            $taskHighest = ($runLevelRaw -eq 1)
        }
        elseif ($runLevelValue) {
            $taskHighest = ($runLevelValue -match "Highest" -or $runLevelValue -eq "1")
        }
        return [ordered]@{
            exists = $true
            enabled = [bool]$task.Settings.Enabled
            last_run_time = if ($taskInfo) { $taskInfo.LastRunTime } else { $null }
            last_task_result = if ($taskInfo) { $taskInfo.LastTaskResult } else { $null }
            run_level = $runLevelValue
            highest = $taskHighest
            user_id = "$($task.Principal.UserId)"
        }
    }
    catch {
        return [ordered]@{
            exists = $false
            enabled = $false
            last_run_time = $null
            last_task_result = $null
            run_level = $null
            highest = $false
            user_id = $null
        }
    }
}

function Test-ShortcutInstalled {
    return (Test-Path $ShortcutPath)
}

function Get-InstallStatus {
    $taskInfo = Get-StartupTaskInfoSafe
    $taskInstalled = [bool]$taskInfo.exists
    $taskEnabled = [bool]$taskInfo.enabled
    $shortcutInstalled = Test-ShortcutInstalled
    $taskUsable = ($taskInstalled -and $taskEnabled)

    $mode = "none"
    if ($taskUsable) {
        $mode = "scheduled_task"
    }
    elseif ($shortcutInstalled) {
        $mode = "startup_shortcut"
    }

    return [ordered]@{
        installed          = ($taskUsable -or $shortcutInstalled)
        mode               = $mode
        task_installed     = $taskInstalled
        task_enabled       = $taskEnabled
        task_last_run_time = $taskInfo.last_run_time
        task_last_result   = $taskInfo.last_task_result
        task_run_level     = $taskInfo.run_level
        task_highest       = [bool]$taskInfo.highest
        task_user_id       = $taskInfo.user_id
        shortcut_installed = $shortcutInstalled
        task_name          = $TaskName
        shortcut_path      = $ShortcutPath
        vbs_path           = $VBSPath
        launcher_path      = $StartupLauncherPath
        user               = $CurrentUser
    }
}

if (($Install -or $Uninstall) -and -not (Test-IsAdministrator)) {
    $forwardArgs = @()
    if ($Install) { $forwardArgs += "-Install" }
    if ($Uninstall) { $forwardArgs += "-Uninstall" }
    if ($Json) { $forwardArgs += "-Json" }
    Invoke-ElevatedSelf -ForwardArgs $forwardArgs
}

function Remove-Shortcut {
    if (Test-Path $ShortcutPath) {
        Remove-Item $ShortcutPath -Force -ErrorAction Stop
    }
}

function Create-Shortcut {
    $WshShell = New-Object -ComObject WScript.Shell
    $Shortcut = $null
    try {
        $Shortcut = $WshShell.CreateShortcut($ShortcutPath)
        $Shortcut.TargetPath = "powershell.exe"
        $Shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$StartupLauncherPath`""
        $Shortcut.WorkingDirectory = $PSScriptRoot
        $Shortcut.Description = "A.B.S.O. System Tray"
        $Shortcut.Save()
    }
    finally {
        if ($Shortcut) {
            [System.Runtime.InteropServices.Marshal]::ReleaseComObject($Shortcut) | Out-Null
        }
        [System.Runtime.InteropServices.Marshal]::ReleaseComObject($WshShell) | Out-Null
    }
}

function Register-StartupTask {
    $taskAction = New-ScheduledTaskAction `
        -Execute "powershell.exe" `
        -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$StartupLauncherPath`""

    try {
        $taskTrigger = New-ScheduledTaskTrigger -AtLogOn -User $CurrentUser -RandomDelay (New-TimeSpan -Seconds 20)
    }
    catch {
        $taskTrigger = New-ScheduledTaskTrigger -AtLogOn -User $CurrentUser
    }

    $taskPrincipal = New-ScheduledTaskPrincipal -UserId $CurrentUser -LogonType Interactive -RunLevel Highest
    $taskSettings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -MultipleInstances IgnoreNew `
        -RestartCount 3 `
        -RestartInterval (New-TimeSpan -Minutes 1) `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $taskAction `
        -Trigger $taskTrigger `
        -Principal $taskPrincipal `
        -Settings $taskSettings `
        -Description $TaskDescription `
        -Force `
        -ErrorAction Stop | Out-Null

    try {
        Enable-ScheduledTask -TaskName $TaskName -ErrorAction Stop | Out-Null
    }
    catch {}
}

function Remove-StartupTask {
    if (Test-StartupTaskInstalled) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop
    }
}

if ($Status) {
    $statusObj = Get-InstallStatus
    if ($Json) {
        Write-JsonResult $statusObj
    }
    elseif ($statusObj.installed) {
        $modeLabel = if ($statusObj.mode -eq "scheduled_task") { "Task Scheduler" } else { "Startup shortcut" }
        Write-Host "A.B.S.O. Tray is installed in Windows startup" -ForegroundColor Green
        Write-Host "Mode: $modeLabel"
        if ($statusObj.task_installed) {
            Write-Host "Task: $($statusObj.task_name)"
        }
        if ($statusObj.shortcut_installed) {
            Write-Host "Shortcut: $($statusObj.shortcut_path)"
        }
    }
    else {
        Write-Host "A.B.S.O. Tray is NOT in Windows startup" -ForegroundColor Yellow
    }
    exit 0
}

if ($Install) {
    $result = [ordered]@{
        success = $false
        mode = "none"
        message = ""
        warning = $null
        error = $null
        status = $null
    }

    if (-not (Test-Path $VBSPath)) {
        $result.error = "ABSO-Tray.vbs not found at: $VBSPath"
        if ($Json) {
            Write-JsonResult $result
        }
        else {
            Write-Host "Error: $($result.error)" -ForegroundColor Red
        }
        exit 1
    }

    if (-not (Test-Path $StartupLauncherPath)) {
        $result.error = "ABSO-StartupLaunch.ps1 not found at: $StartupLauncherPath"
        if ($Json) {
            Write-JsonResult $result
        }
        else {
            Write-Host "Error: $($result.error)" -ForegroundColor Red
        }
        exit 1
    }

    try {
        Register-StartupTask
        try {
            Remove-Shortcut
        }
        catch {
            # Best-effort cleanup; task registration is the primary mechanism.
        }
        $result.success = $true
        $result.mode = "scheduled_task"
        $result.message = "A.B.S.O. Tray registered via Task Scheduler."
    }
    catch {
        $taskError = "$($_.Exception.Message)"
        $taskAlreadyInstalled = Test-StartupTaskInstalled

        if ($taskAlreadyInstalled) {
            $result.success = $true
            $result.mode = "scheduled_task"
            $result.warning = "Task Scheduler update failed, but an existing startup task is already installed: $taskError"
            $result.message = "A.B.S.O. Tray will continue using the existing startup task."
            try {
                Remove-Shortcut
            }
            catch {
                # Non-fatal cleanup issue.
            }
        }
        else {
            $result.warning = "Task Scheduler install failed: $taskError"
            try {
                Create-Shortcut
                $result.success = $true
                $result.mode = "startup_shortcut"
                $result.message = "A.B.S.O. Tray registered via Startup shortcut fallback."
            }
            catch {
                $result.error = "Startup shortcut install failed: $($_.Exception.Message)"
            }
        }
    }

    $result.status = Get-InstallStatus

    if ($Json) {
        Write-JsonResult $result
    }
    elseif ($result.success) {
        Write-Host "A.B.S.O. Tray added to Windows startup" -ForegroundColor Green
        Write-Host "Mode: $($result.mode)"
        if ($result.warning) {
            Write-Host "Warning: $($result.warning)" -ForegroundColor Yellow
        }
        Write-Host ""
        Write-Host "The tray will start automatically on next login."
        Write-Host "To start now, run: powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$StartupLauncherPath`""
    }
    else {
        Write-Host "Failed to add A.B.S.O. Tray to startup" -ForegroundColor Red
        if ($result.warning) {
            Write-Host "Warning: $($result.warning)" -ForegroundColor Yellow
        }
        if ($result.error) {
            Write-Host "Error: $($result.error)" -ForegroundColor Red
        }
        exit 1
    }

    exit 0
}

if ($Uninstall) {
    $result = [ordered]@{
        success = $true
        removed_task = $false
        removed_shortcut = $false
        error = $null
        status = $null
    }

    try {
        if (Test-StartupTaskInstalled) {
            Remove-StartupTask
            $result.removed_task = $true
        }
    }
    catch {
        $result.success = $false
        $result.error = "Failed removing scheduled task: $($_.Exception.Message)"
    }

    try {
        if (Test-ShortcutInstalled) {
            Remove-Shortcut
            $result.removed_shortcut = $true
        }
    }
    catch {
        $result.success = $false
        if ($result.error) {
            $result.error += "; Failed removing shortcut: $($_.Exception.Message)"
        }
        else {
            $result.error = "Failed removing shortcut: $($_.Exception.Message)"
        }
    }

    $result.status = Get-InstallStatus

    if ($Json) {
        Write-JsonResult $result
    }
    elseif ($result.success) {
        if ($result.removed_task -or $result.removed_shortcut) {
            Write-Host "A.B.S.O. Tray removed from Windows startup" -ForegroundColor Green
        }
        else {
            Write-Host "A.B.S.O. Tray was not registered in startup" -ForegroundColor Yellow
        }
    }
    else {
        Write-Host "Failed to fully remove startup registration" -ForegroundColor Red
        Write-Host "Error: $($result.error)" -ForegroundColor Red
        exit 1
    }

    exit 0
}

# Default: show usage
Write-Host ""
Write-Host "A.B.S.O. Tray Startup Installer" -ForegroundColor Cyan
Write-Host ""
Write-Host "Usage:"
Write-Host "  -Install         Add A.B.S.O. tray to Windows startup"
Write-Host "  -Uninstall       Remove from startup"
Write-Host "  -Status          Check if installed in startup"
Write-Host "  -Status -Json    Emit machine-readable status"
Write-Host ""
