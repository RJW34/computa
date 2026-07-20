# install.ps1 - computa end-user installer.
#
# Default mode is a small guided setup window (no console output): the user
# sees what was found on their PC, toggles what setup may do, and watches
# plain-English progress. Installing NEVER applies a profile - game and
# Windows settings only change later, from the tray, when the user chooses.
#
# The window drives the computa.exe backend:
#   computa setup --plan --json     read-only preflight shown before install
#   computa setup --unattended ...  executes exactly the toggled actions,
#                                   streaming JSON progress lines
#
# Ship this script (and "Install computa.cmd") next to computa.exe as
# release assets.
#
# Usage:
#   Double-click "Install computa.cmd"        friendly window (recommended)
#   powershell -File .\install.ps1            same window, from a terminal
#   powershell -File .\install.ps1 -Console   classic text-mode install
#
# Testing switches (not for end users):
#   -SafeDefaults   toggles that mutate the real system default to OFF
#                   (sandbox harness runs)
#   -PreviewUi options|progress|done|failed   render a page with canned data
#   -PreviewShot <path.png>                   with -PreviewUi: save a
#                                             screenshot and exit

param(
    [string]$ExePath = "",
    [switch]$Console,
    [switch]$NoSetup,
    [switch]$NoPath,
    [switch]$SafeDefaults,
    [ValidateSet("", "options", "progress", "done", "failed")]
    [string]$PreviewUi = "",
    [string]$PreviewShot = ""
)

$ErrorActionPreference = "Stop"

$script:InstallRoot = Join-Path $env:LOCALAPPDATA "AdaptiveBattleStationOptimizer"
$script:InstalledExe = Join-Path $script:InstallRoot "computa.exe"

# Resolve the source executable: explicit param, else next to this script.
if ([string]::IsNullOrWhiteSpace($ExePath)) {
    $ExePath = Join-Path $PSScriptRoot "computa.exe"
}

# ---------------------------------------------------------------------------
# Classic console flow (power users, CI)
# ---------------------------------------------------------------------------
function Invoke-ConsoleInstall {
    if (-not (Test-Path $ExePath)) {
        Write-Host "computa.exe not found at: $ExePath" -ForegroundColor Red
        Write-Host "Download computa.exe from the latest release and place it next to this script,"
        Write-Host "or pass -ExePath <path-to-computa.exe>."
        exit 1
    }

    Write-Host ""
    Write-Host "computa installer" -ForegroundColor Cyan
    Write-Host "  Source:  $ExePath"
    Write-Host "  Target:  $script:InstalledExe"
    Write-Host ""

    New-Item -ItemType Directory -Force -Path $script:InstallRoot | Out-Null
    Copy-Item -Path $ExePath -Destination $script:InstalledExe -Force
    Write-Host "Installed computa.exe." -ForegroundColor Green

    if (-not $NoPath) {
        Add-InstallDirToUserPath | Out-Null
        Write-Host "Install folder is on the user PATH." -ForegroundColor Green
    }

    if ($NoSetup) {
        Write-Host ""
        Write-Host "Skipped setup. Run this later from an elevated terminal:" -ForegroundColor Yellow
        Write-Host "  computa setup"
        exit 0
    }

    Write-Host ""
    Write-Host "Launching the first-run setup wizard (requires administrator approval)..." -ForegroundColor Cyan
    try {
        Start-Process -FilePath $script:InstalledExe -ArgumentList "setup" -Verb RunAs -Wait
    }
    catch {
        Write-Host "Setup was not started ($($_.Exception.Message))." -ForegroundColor Yellow
        Write-Host "Run it yourself from an elevated terminal:  computa setup"
    }

    Write-Host ""
    Write-Host "Done. Useful commands:" -ForegroundColor Cyan
    Write-Host "  computa profiles      list profiles available on this machine"
    Write-Host "  computa apply <id>    apply a profile (automatic backup first)"
    Write-Host "  computa restore latest  roll back the last apply"
    Write-Host "  computa uninstall     restore the setup baseline and remove computa"
    exit 0
}

function Add-InstallDirToUserPath {
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if ($null -eq $userPath) { $userPath = "" }
    $onPath = ($userPath -split ";" | Where-Object { $_.TrimEnd("\") -ieq $script:InstallRoot.TrimEnd("\") }).Count -gt 0
    if (-not $onPath) {
        $newPath = if ([string]::IsNullOrWhiteSpace($userPath)) { $script:InstallRoot } else { "$userPath;$script:InstallRoot" }
        [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
        return $true
    }
    return $false
}

if ($Console) { Invoke-ConsoleInstall }

# ---------------------------------------------------------------------------
# GUI flow
# ---------------------------------------------------------------------------
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

if (-not ("ComputaInstaller.Native" -as [type])) {
    Add-Type -Namespace ComputaInstaller -Name Native -MemberDefinition @'
[DllImport("dwmapi.dll")]
public static extern int DwmSetWindowAttribute(IntPtr hwnd, int attr, ref int attrValue, int attrSize);
[DllImport("user32.dll")]
public static extern bool SetProcessDPIAware();
'@
}
[ComputaInstaller.Native]::SetProcessDPIAware() | Out-Null

$previewMode = -not [string]::IsNullOrWhiteSpace($PreviewUi)

# Elevation: the unattended backend needs admin. Relaunch hidden so no console
# window ever appears for the end user. (Previews render without admin.)
$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $previewMode -and -not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    $argList = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", "`"$PSCommandPath`"")
    if ($PSBoundParameters.ContainsKey("ExePath")) { $argList += @("-ExePath", "`"$ExePath`"") }
    if ($SafeDefaults) { $argList += "-SafeDefaults" }
    try {
        Start-Process powershell.exe -Verb RunAs -WindowStyle Hidden -ArgumentList $argList
    }
    catch {
        [System.Windows.Forms.MessageBox]::Show(
            "computa setup needs administrator approval to continue.",
            "computa setup",
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Information) | Out-Null
    }
    exit
}

if (-not $previewMode -and -not (Test-Path $ExePath)) {
    [System.Windows.Forms.MessageBox]::Show(
        "computa.exe was not found next to this installer.`n`nExpected: $ExePath`n`nDownload computa.exe from the latest release and keep it in the same folder as the installer.",
        "computa setup",
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Warning) | Out-Null
    exit 1
}

# --- palette (phosphor instrument system, matches tray + GUI) --------------
$Ink0    = [System.Drawing.Color]::FromArgb(255, 4, 15, 18)
$Ink300  = [System.Drawing.Color]::FromArgb(255, 11, 35, 42)
$Ink600  = [System.Drawing.Color]::FromArgb(255, 25, 82, 90)
$Paper   = [System.Drawing.Color]::FromArgb(255, 225, 244, 240)
$Mist    = [System.Drawing.Color]::FromArgb(255, 148, 183, 182)
$Signal  = [System.Drawing.Color]::FromArgb(255, 0, 245, 212)
$Warning = [System.Drawing.Color]::FromArgb(255, 245, 184, 64)
$Danger  = [System.Drawing.Color]::FromArgb(255, 240, 90, 90)

# --- glyphs (char codes: this file must survive ANSI-assuming hosts) -------
$GlyphPending = [string][char]0x00B7   # middle dot
$GlyphRunning = [string][char]0x25B8   # small right triangle
$GlyphOk      = [string][char]0x2713   # check mark
$GlyphSkip    = [string][char]0x2013   # en dash
$GlyphError   = [string][char]0x2715   # multiplication x
$GlyphBullet  = [string][char]0x2022   # bullet

# --- fonts (resolver stacks; Bahnschrift/Cascadia ship with Windows 11) ----
function New-InstallerFont {
    param([string[]]$Families, [single]$Size, [System.Drawing.FontStyle]$Style = [System.Drawing.FontStyle]::Regular)
    foreach ($family in $Families) {
        try {
            $font = New-Object System.Drawing.Font($family, $Size, $Style)
            if ($font.Name -eq $family) { return $font }
            $font.Dispose()
        } catch {}
    }
    New-Object System.Drawing.Font("Segoe UI", $Size, $Style)
}

$HeroStack    = @("Bahnschrift", "Segoe UI Variable Display", "Segoe UI")
$EyebrowStack = @("Cascadia Mono SemiBold", "Cascadia Mono", "Consolas", "Segoe UI")

$FontWordmark = New-InstallerFont $HeroStack 20.0 ([System.Drawing.FontStyle]::Bold)
$FontHeading  = New-InstallerFont $HeroStack 13.0 ([System.Drawing.FontStyle]::Bold)
$FontBody     = New-InstallerFont $HeroStack 9.75
$FontSub      = New-InstallerFont $HeroStack 8.5
$FontEyebrow  = New-InstallerFont $EyebrowStack 8.25
$FontButton   = New-InstallerFont $HeroStack 10.0 ([System.Drawing.FontStyle]::Bold)
$FontGlyph    = New-InstallerFont $EyebrowStack 9.5

# --- DPI-scaled layout helpers ---------------------------------------------
$gProbe = [System.Drawing.Graphics]::FromHwnd([IntPtr]::Zero)
$script:UiScale = $gProbe.DpiX / 96.0
$gProbe.Dispose()
function S { param([double]$Value) [int][math]::Round($Value * $script:UiScale) }

$PadX = S 24
$ContentW = (S 480) - (2 * $PadX)

function Measure-WrapHeight {
    param([string]$Text, [System.Drawing.Font]$Font, [int]$Width)
    $size = [System.Windows.Forms.TextRenderer]::MeasureText(
        $Text, $Font,
        (New-Object System.Drawing.Size($Width, [int]::MaxValue)),
        [System.Windows.Forms.TextFormatFlags]::WordBreak)
    $size.Height
}

function New-UiLabel {
    param(
        [System.Windows.Forms.Control]$Parent,
        [string]$Text,
        [System.Drawing.Font]$Font,
        [System.Drawing.Color]$Color,
        [int]$X, [int]$Y, [int]$Width,
        [int]$Height = 0
    )
    $label = New-Object System.Windows.Forms.Label
    $label.Text = $Text
    $label.Font = $Font
    $label.ForeColor = $Color
    $label.BackColor = $Ink0
    $label.AutoSize = $false
    if ($Height -le 0) { $Height = Measure-WrapHeight $Text $Font $Width }
    $label.SetBounds($X, $Y, $Width, $Height)
    $Parent.Controls.Add($label)
    $label
}

function New-Eyebrow {
    param([System.Windows.Forms.Control]$Parent, [string]$Text, [int]$Y)
    $label = New-Object System.Windows.Forms.Label
    $label.Text = $Text.ToUpperInvariant()
    $label.Font = $FontEyebrow
    $label.ForeColor = $Mist
    $label.BackColor = $Ink0
    $label.AutoSize = $true
    $label.Location = New-Object System.Drawing.Point($PadX, $Y)
    $Parent.Controls.Add($label)
    $textW = [System.Windows.Forms.TextRenderer]::MeasureText($label.Text, $FontEyebrow).Width
    $rule = New-Object System.Windows.Forms.Panel
    $rule.BackColor = $Ink600
    $ruleX = $PadX + $textW + (S 8)
    $rule.SetBounds($ruleX, $Y + (S 6), ($PadX + $ContentW) - $ruleX, 1)
    $Parent.Controls.Add($rule)
    $label
}

function New-OptionRow {
    param(
        [System.Windows.Forms.Control]$Parent,
        [string]$Title,
        [string]$Sub,
        [bool]$Checked,
        [int]$Y,
        [System.Drawing.Color]$TitleColor
    )
    $check = New-Object System.Windows.Forms.CheckBox
    $check.Text = $Title
    $check.Font = $FontBody
    $check.ForeColor = $TitleColor
    $check.BackColor = $Ink0
    $check.FlatStyle = [System.Windows.Forms.FlatStyle]::Flat
    $check.Checked = $Checked
    $check.AutoSize = $false
    $check.SetBounds($PadX, $Y, $ContentW, (S 22))
    $Parent.Controls.Add($check)
    $subX = $PadX + (S 22)
    $subLabel = New-UiLabel -Parent $Parent -Text $Sub -Font $FontSub -Color $Mist -X $subX -Y ($Y + (S 22)) -Width ($ContentW - (S 22))
    @{ Check = $check; Sub = $subLabel; Bottom = $subLabel.Bottom }
}

function New-InstallerButton {
    param(
        [System.Windows.Forms.Control]$Parent,
        [string]$Text,
        [int]$X, [int]$Y, [int]$Width,
        [bool]$Primary
    )
    $button = New-Object System.Windows.Forms.Button
    $button.Text = $Text
    $button.Font = $FontButton
    $button.FlatStyle = [System.Windows.Forms.FlatStyle]::Flat
    $button.SetBounds($X, $Y, $Width, (S 34))
    if ($Primary) {
        $button.BackColor = $Signal
        $button.ForeColor = $Ink0
        $button.FlatAppearance.BorderSize = 0
    }
    else {
        $button.BackColor = $Ink0
        $button.ForeColor = $Mist
        $button.FlatAppearance.BorderSize = 1
        $button.FlatAppearance.BorderColor = $Ink600
    }
    $Parent.Controls.Add($button)
    $button
}

# --- form ------------------------------------------------------------------
$form = New-Object System.Windows.Forms.Form
$form.Text = "computa setup"
$form.ClientSize = New-Object System.Drawing.Size((S 480), (S 596))
$form.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::FixedSingle
$form.MaximizeBox = $false
$form.StartPosition = [System.Windows.Forms.FormStartPosition]::CenterScreen
$form.BackColor = $Ink0
$form.ForeColor = $Paper
$form.Font = $FontBody
$form.Add_HandleCreated({
    foreach ($attr in 20, 19) {
        $value = 1
        $result = [ComputaInstaller.Native]::DwmSetWindowAttribute($form.Handle, $attr, [ref]$value, 4)
        if ($result -eq 0) { break }
    }
})

# Header (shared by every page)
New-UiLabel -Parent $form -Text "computa" -Font $FontWordmark -Color $Paper -X $PadX -Y (S 16) -Width $ContentW | Out-Null
New-UiLabel -Parent $form -Text "per-game Windows optimization, with a backup of everything it touches" -Font $FontSub -Color $Mist -X $PadX -Y (S 48) -Width $ContentW | Out-Null
$headerRule = New-Object System.Windows.Forms.Panel
$headerRule.BackColor = $Ink600
$headerRule.SetBounds($PadX, (S 74), $ContentW, 1)
$form.Controls.Add($headerRule)

$pageTop = S 84
$pageH = $form.ClientSize.Height - $pageTop

function New-Page {
    $panel = New-Object System.Windows.Forms.Panel
    $panel.SetBounds(0, $pageTop, (S 480), $pageH)
    $panel.BackColor = $Ink0
    $panel.Visible = $false
    $form.Controls.Add($panel)
    $panel
}

$pageOptions = New-Page
$pageProgress = New-Page
$pageDone = New-Page

function Show-Page {
    param([System.Windows.Forms.Panel]$Page)
    foreach ($p in @($pageOptions, $pageProgress, $pageDone)) { $p.Visible = ($p -eq $Page) }
}

# --- options page ----------------------------------------------------------
$y = S 6
$blurb = "This sets up computa on your PC. Installing changes none of your Windows or game settings - when you're ready, you pick a game profile from the tray icon, and every change is backed up first."
$lblBlurb = New-UiLabel -Parent $pageOptions -Text $blurb -Font $FontBody -Color $Paper -X $PadX -Y $y -Width $ContentW
$y = $lblBlurb.Bottom + (S 14)

New-Eyebrow -Parent $pageOptions -Text "Your PC" -Y $y | Out-Null
$y += S 20
$lblHardware = New-UiLabel -Parent $pageOptions -Text "Taking a look at your PC..." -Font $FontBody -Color $Paper -X $PadX -Y $y -Width $ContentW -Height (S 51)
$y = $lblHardware.Bottom + (S 2)
$lblPcNotes = New-UiLabel -Parent $pageOptions -Text " " -Font $FontSub -Color $Mist -X $PadX -Y $y -Width $ContentW -Height (S 32)
$y = $lblPcNotes.Bottom + (S 12)

New-Eyebrow -Parent $pageOptions -Text "Setup options" -Y $y | Out-Null
$y += S 22

$rowSnapshot = New-OptionRow -Parent $pageOptions -Title "Keep a safety snapshot of this PC's settings (recommended)" -Sub "Records everything computa could ever touch, exactly as it is right now. One click puts it all back." -Checked $true -Y $y -TitleColor $Paper
$y = $rowSnapshot.Bottom + (S 10)

$rowTray = New-OptionRow -Parent $pageOptions -Title "Start the computa tray with Windows" -Sub "A small icon by the clock for switching game profiles. No windows, no popups." -Checked (-not $SafeDefaults) -Y $y -TitleColor $Paper
$y = $rowTray.Bottom + (S 10)

$rowPath = New-OptionRow -Parent $pageOptions -Title "Let me run 'computa' from the command line" -Sub "Adds the install folder to your PATH. Optional - the tray does everything most people need." -Checked (-not $SafeDefaults) -Y $y -TitleColor $Paper
$y = $rowPath.Bottom + (S 10)

# Problematic-update row: hidden until the preflight actually finds one.
$rowKb = New-OptionRow -Parent $pageOptions -Title " " -Sub " " -Checked (-not $SafeDefaults) -Y $y -TitleColor $Warning
$rowKb.Check.Visible = $false
$rowKb.Sub.Visible = $false
$script:PlanKbIds = @()

$buttonY = $pageH - (S 52)
$btnInstall = New-InstallerButton -Parent $pageOptions -Text "Install" -X ($PadX + $ContentW - (S 116)) -Y $buttonY -Width (S 116) -Primary $true
$btnCancel = New-InstallerButton -Parent $pageOptions -Text "Cancel" -X ($PadX + $ContentW - (S 116) - (S 10) - (S 92)) -Y $buttonY -Width (S 92) -Primary $false
$form.AcceptButton = $btnInstall
$btnCancel.Add_Click({ $form.Close() })

# --- progress page ---------------------------------------------------------
$lblProgressHead = New-UiLabel -Parent $pageProgress -Text "Installing..." -Font $FontHeading -Color $Paper -X $PadX -Y (S 6) -Width $ContentW
$script:StepRows = @{}
$script:StepErrors = @()
$script:StepsTop = $lblProgressHead.Bottom + (S 14)
$lblProgressFoot = New-UiLabel -Parent $pageProgress -Text "Nothing else on this PC changes until you choose a game profile later." -Font $FontSub -Color $Mist -X $PadX -Y ($pageH - (S 40)) -Width $ContentW

function Add-StepRow {
    param([string]$Id, [string]$Label)
    $rowY = $script:StepsTop + ($script:StepRows.Count * (S 30))
    $glyph = New-UiLabel -Parent $pageProgress -Text $GlyphPending -Font $FontGlyph -Color $Mist -X $PadX -Y $rowY -Width (S 20) -Height (S 20)
    $text = New-UiLabel -Parent $pageProgress -Text $Label -Font $FontBody -Color $Mist -X ($PadX + (S 24)) -Y $rowY -Width ($ContentW - (S 24)) -Height (S 20)
    $script:StepRows[$Id] = @{ Glyph = $glyph; Text = $text }
}

function Update-StepRow {
    param([string]$Id, [string]$Status, [string]$Detail)
    if (-not $script:StepRows.ContainsKey($Id)) { return }
    $row = $script:StepRows[$Id]
    switch ($Status) {
        "running" { $row.Glyph.Text = $GlyphRunning; $row.Glyph.ForeColor = $Signal; $row.Text.ForeColor = $Paper }
        "ok"      { $row.Glyph.Text = $GlyphOk; $row.Glyph.ForeColor = $Signal; $row.Text.ForeColor = $Paper }
        "skipped" { $row.Glyph.Text = $GlyphSkip; $row.Glyph.ForeColor = $Mist; $row.Text.ForeColor = $Mist }
        "error"   {
            $row.Glyph.Text = $GlyphError; $row.Glyph.ForeColor = $Danger; $row.Text.ForeColor = $Paper
            if ($Detail) { $script:StepErrors += "$($row.Text.Text): $Detail" }
            else { $script:StepErrors += $row.Text.Text }
        }
    }
}

# --- done page -------------------------------------------------------------
$lblDoneHead = New-UiLabel -Parent $pageDone -Text "You're all set." -Font $FontHeading -Color $Paper -X $PadX -Y (S 6) -Width $ContentW
$lblDoneBody = New-UiLabel -Parent $pageDone -Text " " -Font $FontBody -Color $Paper -X $PadX -Y ($lblDoneHead.Bottom + (S 12)) -Width $ContentW -Height (S 160)
$lblDoneReboot = New-UiLabel -Parent $pageDone -Text " " -Font $FontSub -Color $Warning -X $PadX -Y ($lblDoneBody.Bottom + (S 4)) -Width $ContentW -Height (S 30)
$lblDonePath = New-Object System.Windows.Forms.Label
$lblDonePath.Font = $FontSub
$lblDonePath.ForeColor = $Mist
$lblDonePath.BackColor = $Ink0
$lblDonePath.AutoSize = $false
$lblDonePath.AutoEllipsis = $true
$lblDonePath.SetBounds($PadX, ($lblDoneReboot.Bottom + (S 4)), $ContentW, (S 18))
$pageDone.Controls.Add($lblDonePath)
$lblDoneUndo = New-UiLabel -Parent $pageDone -Text "Changed your mind later? Run 'computa uninstall' - the snapshot from today puts everything back the way it was." -Font $FontSub -Color $Mist -X $PadX -Y ($lblDonePath.Bottom + (S 4)) -Width $ContentW

$doneButtonY = $pageH - (S 52)
$btnOpenTray = New-InstallerButton -Parent $pageDone -Text "Open the tray now" -X ($PadX + $ContentW - (S 170)) -Y $doneButtonY -Width (S 170) -Primary $true
$btnClose = New-InstallerButton -Parent $pageDone -Text "Close" -X ($PadX + $ContentW - (S 170) - (S 10) - (S 92)) -Y $doneButtonY -Width (S 92) -Primary $false
$btnClose.Add_Click({ $form.Close() })
$btnOpenTray.Add_Click({
    try {
        Start-Process -FilePath $script:InstalledExe -ArgumentList "tray" -WindowStyle Hidden
    } catch {}
    $form.Close()
})

# --- plan preflight (read-only) --------------------------------------------
function Apply-PlanToUi {
    param($Plan)
    $lines = @()
    if ($Plan.hardware.gpu) { $lines += "GPU      $($Plan.hardware.gpu)" }
    if ($Plan.hardware.cpu) { $lines += "CPU      $($Plan.hardware.cpu)" }
    if ($Plan.hardware.monitor) {
        $monLine = "Display  $($Plan.hardware.monitor)"
        if ($Plan.hardware.monitor_count -gt 1) { $monLine += "  (x$($Plan.hardware.monitor_count))" }
        $lines += $monLine
    }
    if ($lines.Count -eq 0) { $lines = @("Couldn't inspect this PC - that's okay, install continues normally.") }
    $lblHardware.Text = $lines -join "`n"

    $notes = @()
    if ($Plan.gpu_vendor_note) { $notes += $Plan.gpu_vendor_note }
    if ($Plan.detected_games -and $Plan.detected_games.Count -gt 0) {
        $names = @()
        foreach ($entry in $Plan.detected_games) { $names += $entry.games }
        $names = @($names | Select-Object -Unique)
        if ($names.Count -gt 4) {
            $notes += "Games spotted: $($names[0..3] -join ', ') + $($names.Count - 4) more"
        }
        else {
            $notes += "Games spotted: $($names -join ', ')"
        }
    }
    $lblPcNotes.Text = ($notes -join "`n")

    if ($Plan.problematic_kbs -and $Plan.problematic_kbs.Count -gt 0) {
        $script:PlanKbIds = @($Plan.problematic_kbs | ForEach-Object { $_.kb_id })
        $first = $Plan.problematic_kbs[0]
        $idText = $script:PlanKbIds -join ", "
        $rowKb.Check.Text = "Remove a Windows update known to cause problems ($idText)"
        $rowKb.Sub.Text = "$($first.affected) Removing it needs a restart later."
        $rowKb.Sub.Height = Measure-WrapHeight $rowKb.Sub.Text $FontSub ($ContentW - (S 22))
        $rowKb.Check.Visible = $true
        $rowKb.Sub.Visible = $true
    }
}

function Start-PlanProbe {
    param([string]$ProbeExe)
    $script:PlanOut = [System.IO.Path]::GetTempFileName()
    try {
        $script:PlanProc = Start-Process -FilePath $ProbeExe -ArgumentList "setup", "--plan" `
            -RedirectStandardOutput $script:PlanOut -WindowStyle Hidden -PassThru
    }
    catch {
        $lblHardware.Text = "Couldn't inspect this PC - that's okay, install continues normally."
        return
    }
    $script:PlanTimer = New-Object System.Windows.Forms.Timer
    $script:PlanTimer.Interval = 300
    $script:PlanDeadline = [DateTime]::UtcNow.AddSeconds(90)
    $script:PlanTimer.Add_Tick({
        if (-not $script:PlanProc.HasExited) {
            if ([DateTime]::UtcNow -gt $script:PlanDeadline) {
                $script:PlanTimer.Stop()
                try { $script:PlanProc.Kill() } catch {}
                $lblHardware.Text = "Couldn't inspect this PC - that's okay, install continues normally."
            }
            return
        }
        $script:PlanTimer.Stop()
        try {
            $raw = [System.IO.File]::ReadAllText($script:PlanOut).Trim()
            if ($raw) { Apply-PlanToUi (ConvertFrom-Json ($raw -split "`n")[0]) }
            else { $lblHardware.Text = "Couldn't inspect this PC - that's okay, install continues normally." }
        }
        catch {
            $lblHardware.Text = "Couldn't inspect this PC - that's okay, install continues normally."
        }
    })
    $script:PlanTimer.Start()
}

# --- install execution -----------------------------------------------------
function Read-NewLines {
    # Tail a redirected-output file without threads: read bytes past the last
    # offset, return only complete lines, keep the partial tail for next tick.
    param([string]$Path)
    if (-not (Test-Path $Path)) { return @() }
    $fs = [System.IO.File]::Open($Path, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
    try {
        if ($fs.Length -le $script:OutOffset) { return @() }
        $fs.Position = $script:OutOffset
        $count = [int]($fs.Length - $script:OutOffset)
        $buffer = New-Object byte[] $count
        $read = $fs.Read($buffer, 0, $count)
        $script:OutOffset += $read
        $text = [System.Text.Encoding]::UTF8.GetString($buffer, 0, $read)
    }
    finally { $fs.Close() }
    $combined = $script:OutPartial + $text
    $parts = $combined -split "`n"
    $script:OutPartial = $parts[$parts.Count - 1]
    if ($parts.Count -le 1) { return @() }
    $complete = $parts[0..($parts.Count - 2)]
    @($complete | ForEach-Object { $_.TrimEnd("`r") } | Where-Object { $_ })
}

function Process-ProgressLine {
    param([string]$Line)
    try { $obj = ConvertFrom-Json $Line } catch { return }
    switch ($obj.event) {
        "start" {
            foreach ($step in $obj.steps) { Add-StepRow -Id $step.id -Label $step.label }
        }
        "step" {
            Update-StepRow -Id $obj.id -Status $obj.status -Detail $obj.detail
        }
        "done" {
            $script:DoneEvent = $obj
        }
    }
}

function Show-DonePage {
    $done = $script:DoneEvent
    $succeeded = ($null -ne $done) -and $done.success

    if ($succeeded) {
        $lblDoneHead.Text = "You're all set."
        $bullets = @("$GlyphBullet computa is installed")
        if ($script:PathAdded) { $bullets += "$GlyphBullet 'computa' works from any new terminal window" }
        if ($done.summary) { foreach ($item in $done.summary) { $bullets += "$GlyphBullet $item" } }
        $bullets += " "
        $bullets += "Open the tray, pick the profile for your game, and computa handles the rest."
        $lblDoneBody.Text = $bullets -join "`n"
        if ($done.needs_reboot) {
            $lblDoneReboot.Text = "One thing to know: a restart is needed to finish ($($done.reboot_reasons -join ', ')). No rush - Windows will pick it up on your next reboot."
        }
        $lblDonePath.Text = "Installed to: $script:InstallRoot"
        $btnOpenTray.Visible = $true
    }
    else {
        $lblDoneHead.Text = "Something didn't finish."
        $lines = @()
        if ($script:StepErrors.Count -gt 0) { $lines += $script:StepErrors }
        elseif ($null -eq $done) { $lines += "The setup process ended unexpectedly." }
        $lines += " "
        $lines += "Everything that did finish is safe, and nothing else on your PC was changed. You can run the installer again, or ask the friend who sent you this to take a look."
        $lblDoneBody.Text = $lines -join "`n"
        $lblDoneHead.ForeColor = $Danger
        $lblDoneUndo.Visible = $false
        $lblDonePath.Visible = $false
        $btnOpenTray.Visible = $false
    }
    Show-Page $pageDone
}

function Start-Install {
    $btnInstall.Enabled = $false
    $btnCancel.Enabled = $false

    try {
        New-Item -ItemType Directory -Force -Path $script:InstallRoot | Out-Null
        Copy-Item -Path $ExePath -Destination $script:InstalledExe -Force
    }
    catch {
        [System.Windows.Forms.MessageBox]::Show(
            "Couldn't copy computa.exe into place:`n$($_.Exception.Message)",
            "computa setup",
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Warning) | Out-Null
        $btnInstall.Enabled = $true
        $btnCancel.Enabled = $true
        return
    }

    $script:PathAdded = $false
    if ($rowPath.Check.Checked) {
        try { Add-InstallDirToUserPath | Out-Null; $script:PathAdded = $true } catch {}
    }

    $backendArgs = @("setup", "--unattended")
    if ($rowSnapshot.Check.Checked) { $backendArgs += "--baseline" } else { $backendArgs += "--no-baseline" }
    $backendArgs += "--config"
    if ($rowTray.Check.Checked) { $backendArgs += "--tray-autostart" } else { $backendArgs += "--no-tray-autostart" }
    if ($rowKb.Check.Visible -and $rowKb.Check.Checked) {
        foreach ($kbId in $script:PlanKbIds) { $backendArgs += @("--remove-kb", $kbId) }
    }

    $script:OutOffset = 0
    $script:OutPartial = ""
    $script:DoneEvent = $null
    $script:InstallOut = [System.IO.Path]::GetTempFileName()
    $script:InstallErr = [System.IO.Path]::GetTempFileName()
    try {
        $script:InstallProc = Start-Process -FilePath $script:InstalledExe -ArgumentList $backendArgs `
            -RedirectStandardOutput $script:InstallOut -RedirectStandardError $script:InstallErr `
            -WindowStyle Hidden -PassThru
    }
    catch {
        $script:StepErrors += "Couldn't start the setup backend: $($_.Exception.Message)"
        Show-DonePage
        return
    }

    Show-Page $pageProgress
    $script:InstallTimer = New-Object System.Windows.Forms.Timer
    $script:InstallTimer.Interval = 200
    $script:InstallTimer.Add_Tick({
        foreach ($line in (Read-NewLines $script:InstallOut)) { Process-ProgressLine $line }
        if ($script:InstallProc.HasExited) {
            foreach ($line in (Read-NewLines $script:InstallOut)) { Process-ProgressLine $line }
            $script:InstallTimer.Stop()
            Show-DonePage
        }
    })
    $script:InstallTimer.Start()
}

$btnInstall.Add_Click({ Start-Install })

# --- preview mode (screenshot harness; canned data, installs nothing) ------
if ($previewMode) {
    $cannedPlan = @'
{"app_version":"1.1.0","is_admin":true,
 "hardware":{"gpu":"NVIDIA GeForce RTX 3080","cpu":"Intel(R) Core(TM) i7-12700K","ram_gb":32.0,"monitor":"Generic PnP Monitor @ 165Hz","monitor_count":2},
 "gpu_vendor":"nvidia","gpu_vendor_note":"NVIDIA GPU - full driver tuning available.",
 "problematic_kbs":[{"kb_id":"KB5074109","title":"Reported NVIDIA FPS regression","affected":"NVIDIA GPUs - reported FPS drops (impact varies by system)."}],
 "detected_games":[{"profile":"counter-strike-2","games":["Counter-Strike 2"]},{"profile":"fortnite","games":["Fortnite"]}]}
'@
    switch ($PreviewUi) {
        "options" {
            Apply-PlanToUi (ConvertFrom-Json $cannedPlan)
            Show-Page $pageOptions
        }
        "progress" {
            Add-StepRow -Id "tray_assets" -Label "Putting the tray helper's files in place"
            Add-StepRow -Id "config" -Label "Creating your settings file"
            Add-StepRow -Id "baseline" -Label "Saving a snapshot of your current settings"
            Add-StepRow -Id "tray_autostart" -Label "Setting the tray to start with Windows"
            Add-StepRow -Id "state" -Label "Finishing up"
            Update-StepRow -Id "tray_assets" -Status "ok"
            Update-StepRow -Id "config" -Status "ok"
            Update-StepRow -Id "baseline" -Status "running"
            Show-Page $pageProgress
        }
        "done" {
            $script:PathAdded = $true
            $script:DoneEvent = ConvertFrom-Json '{"event":"done","success":true,"needs_reboot":false,"reboot_reasons":[],"baseline_backup_id":"2026-07-20_120000","summary":["Settings file created","Safety snapshot saved (2026-07-20_120000)","Tray will start with Windows"]}'
            Show-DonePage
        }
        "failed" {
            $script:StepErrors = @("Saving a snapshot of your current settings: access was denied")
            $script:DoneEvent = ConvertFrom-Json '{"event":"done","success":false,"needs_reboot":false,"reboot_reasons":[],"summary":[]}'
            Show-DonePage
        }
    }

    if (-not [string]::IsNullOrWhiteSpace($PreviewShot)) {
        # DrawToBitmap renders the control tree directly - immune to z-order,
        # unlike CopyFromScreen (which captures whatever covers the form).
        $form.TopMost = $true
        $form.Show()
        [System.Windows.Forms.Application]::DoEvents()
        Start-Sleep -Milliseconds 300
        [System.Windows.Forms.Application]::DoEvents()
        $bmp = New-Object System.Drawing.Bitmap($form.Width, $form.Height)
        $form.DrawToBitmap($bmp, (New-Object System.Drawing.Rectangle(0, 0, $form.Width, $form.Height)))
        $bmp.Save($PreviewShot, [System.Drawing.Imaging.ImageFormat]::Png)
        $bmp.Dispose()
        $form.Close()
        Write-Output "captured: $PreviewShot ($($form.Width)x$($form.Height))"
        exit 0
    }

    [System.Windows.Forms.Application]::Run($form)
    exit 0
}

# --- run -------------------------------------------------------------------
Show-Page $pageOptions
$form.Add_Shown({ Start-PlanProbe -ProbeExe $ExePath })
[System.Windows.Forms.Application]::Run($form)
