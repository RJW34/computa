# ABSO-FirstRun.ps1 - computa first-time setup window.
#
# Launched by the installer's finish page (via ABSO-FirstRun.vbs, no console)
# or anytime later from the installed tray directory. computa.exe is already
# installed when this runs; this window handles onboarding only:
#
#   - shows what was found on the PC (hardware, games, problematic updates)
#   - asks what setup may do (safety snapshot, tray autostart, KB removal)
#   - surveys games + display (HDR/VRR/capture) to tune the tray's list
#   - streams plain-English progress from: computa setup --unattended ...
#
# It NEVER applies a profile - game and Windows settings only change later,
# from the tray, when the user chooses.
#
# Testing switches (not for end users):
#   -SafeDefaults   toggles that mutate the real system default to OFF
#   -BackendExe     explicit path to computa.exe (default: two dirs up)
#   -PreviewUi options|survey|progress|done|failed   render a page canned
#   -PreviewShot <path.png>   with -PreviewUi: save a screenshot and exit

param(
    [switch]$SafeDefaults,
    [string]$BackendExe = "",
    [ValidateSet("", "options", "survey", "progress", "done", "failed")]
    [string]$PreviewUi = "",
    [string]$PreviewShot = ""
)

$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

if (-not ("ComputaFirstRun.Native" -as [type])) {
    Add-Type -Namespace ComputaFirstRun -Name Native -MemberDefinition @'
[DllImport("dwmapi.dll")]
public static extern int DwmSetWindowAttribute(IntPtr hwnd, int attr, ref int attrValue, int attrSize);
[DllImport("user32.dll")]
public static extern bool SetProcessDPIAware();
'@
}
[ComputaFirstRun.Native]::SetProcessDPIAware() | Out-Null

$previewMode = -not [string]::IsNullOrWhiteSpace($PreviewUi)

# Resolve the backend exe: installed layout is {app}\abso\tray\ (this script)
# with computa.exe at {app}\computa.exe; repo layout falls back to dist\.
if ([string]::IsNullOrWhiteSpace($BackendExe)) {
    $candidates = @(
        (Join-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) "computa.exe"),
        (Join-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) "dist\computa.exe")
    )
    $BackendExe = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $BackendExe) { $BackendExe = $candidates[0] }
}
$script:InstallRoot = Split-Path $BackendExe -Parent

# Elevation: the setup backend needs admin. Relaunch hidden so no console
# window ever appears for the end user. (Previews render without admin.)
$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $previewMode -and -not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    $argList = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", "`"$PSCommandPath`"", "-BackendExe", "`"$BackendExe`"")
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

if (-not $previewMode -and -not (Test-Path $BackendExe)) {
    [System.Windows.Forms.MessageBox]::Show(
        "computa.exe was not found.`n`nExpected: $BackendExe`n`nReinstall computa, or run this from the installed folder.",
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
        $result = [ComputaFirstRun.Native]::DwmSetWindowAttribute($form.Handle, $attr, [ref]$value, 4)
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
$pageSurvey = New-Page
$pageProgress = New-Page
$pageDone = New-Page

function Show-Page {
    param([System.Windows.Forms.Panel]$Page)
    foreach ($p in @($pageOptions, $pageSurvey, $pageProgress, $pageDone)) { $p.Visible = ($p -eq $Page) }
}

# --- options page ----------------------------------------------------------
$y = S 6
$blurb = "computa is installed. This one-time setup looks at your PC and prepares the tray - none of your Windows or game settings change until you pick a game profile later, always with a backup first."
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

# Problematic-update row: hidden until the preflight actually finds one.
$rowKb = New-OptionRow -Parent $pageOptions -Title " " -Sub " " -Checked (-not $SafeDefaults) -Y $y -TitleColor $Warning
$rowKb.Check.Visible = $false
$rowKb.Sub.Visible = $false
$script:PlanKbIds = @()

$buttonY = $pageH - (S 52)
$btnNext = New-InstallerButton -Parent $pageOptions -Text "Next" -X ($PadX + $ContentW - (S 116)) -Y $buttonY -Width (S 116) -Primary $true
$btnCancel = New-InstallerButton -Parent $pageOptions -Text "Later" -X ($PadX + $ContentW - (S 116) - (S 10) - (S 92)) -Y $buttonY -Width (S 92) -Primary $false
$form.AcceptButton = $btnNext
$btnCancel.Add_Click({ $form.Close() })

# --- survey page (what do you play, what's your display) -------------------
$y = S 6
New-Eyebrow -Parent $pageSurvey -Text "Your games" -Y $y | Out-Null
$y += S 18
$surveyNote = New-UiLabel -Parent $pageSurvey -Text "Check what you play - the tray menu only shows profiles for those games. Desktop profiles are always included; leave everything unchecked to keep the full list." -Font $FontSub -Color $Mist -X $PadX -Y $y -Width $ContentW
$y = $surveyNote.Bottom + (S 6)

# Owner-drawn phosphor check lists. NOT CheckedListBox: that control
# owner-draws its items internally and never raises the public DrawItem
# event, so its themed white boxes, blue selection bar, and focus cues
# cannot be restyled. A plain ListBox with SelectionMode None + our own
# check state (in .Tag) draws everything on the system: static hairline
# frame, flat check squares, quiet ink hover, no selection concept at all.
function New-PhosphorCheckList {
    param(
        [System.Windows.Forms.Control]$Parent,
        [int]$X, [int]$Y, [int]$Width,
        [int]$RowCount
    )
    $frame = New-Object System.Windows.Forms.Panel
    $frame.BackColor = $Ink600
    $frame.SetBounds($X, $Y, $Width, (2 + $RowCount * (S 19)))
    $Parent.Controls.Add($frame)

    $list = New-Object System.Windows.Forms.ListBox
    $list.BackColor = $Ink0
    $list.ForeColor = $Paper
    $list.BorderStyle = [System.Windows.Forms.BorderStyle]::None
    $list.SelectionMode = [System.Windows.Forms.SelectionMode]::None
    $list.IntegralHeight = $false
    $list.Font = $FontBody
    $list.DrawMode = [System.Windows.Forms.DrawMode]::OwnerDrawFixed
    $list.ItemHeight = S 19
    $list.SetBounds(1, 1, $frame.Width - 2, $frame.Height - 2)
    $list.Tag = @{ Checked = (New-Object System.Collections.ArrayList); Hot = -1 }
    $frame.Controls.Add($list)

    $list.add_MouseClick({
        param($sender, $e)
        $index = $sender.IndexFromPoint($e.Location)
        if ($index -ge 0 -and $index -lt $sender.Tag.Checked.Count) {
            $sender.Tag.Checked[$index] = -not $sender.Tag.Checked[$index]
            $sender.Invalidate()
        }
    })
    $list.add_MouseMove({
        param($sender, $e)
        $hot = $sender.IndexFromPoint($e.Location)
        if ($hot -ne $sender.Tag.Hot) {
            $sender.Tag.Hot = $hot
            $sender.Invalidate()
        }
    })
    $list.add_MouseLeave({
        param($sender, $e)
        if ($sender.Tag.Hot -ne -1) {
            $sender.Tag.Hot = -1
            $sender.Invalidate()
        }
    })
    $list.add_DrawItem({
        param($sender, $e)
        if ($e.Index -lt 0) { return }
        $rowBack = $Ink0
        if ($e.Index -eq $sender.Tag.Hot) { $rowBack = $Ink300 }
        $backBrush = New-Object System.Drawing.SolidBrush($rowBack)
        $e.Graphics.FillRectangle($backBrush, $e.Bounds)
        $backBrush.Dispose()

        $boxSize = S 13
        $boxX = $e.Bounds.X + (S 6)
        $boxY = $e.Bounds.Y + [int](($e.Bounds.Height - $boxSize) / 2)
        $isChecked = ($e.Index -lt $sender.Tag.Checked.Count) -and $sender.Tag.Checked[$e.Index]
        if ($isChecked) {
            $fillBrush = New-Object System.Drawing.SolidBrush($Signal)
            $e.Graphics.FillRectangle($fillBrush, $boxX, $boxY, $boxSize, $boxSize)
            $fillBrush.Dispose()
            $oldSmoothing = $e.Graphics.SmoothingMode
            $e.Graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
            $checkPen = New-Object System.Drawing.Pen($Ink0, [single]([math]::Max(1.5, $boxSize / 8.0)))
            $points = @(
                (New-Object System.Drawing.PointF(($boxX + $boxSize * 0.22), ($boxY + $boxSize * 0.52))),
                (New-Object System.Drawing.PointF(($boxX + $boxSize * 0.42), ($boxY + $boxSize * 0.74))),
                (New-Object System.Drawing.PointF(($boxX + $boxSize * 0.80), ($boxY + $boxSize * 0.28)))
            )
            $e.Graphics.DrawLines($checkPen, $points)
            $checkPen.Dispose()
            $e.Graphics.SmoothingMode = $oldSmoothing
        }
        else {
            $boxPen = New-Object System.Drawing.Pen($Mist, 1)
            $e.Graphics.DrawRectangle($boxPen, $boxX, $boxY, $boxSize - 1, $boxSize - 1)
            $boxPen.Dispose()
        }

        $textX = $boxX + $boxSize + (S 8)
        $textRect = New-Object System.Drawing.Rectangle($textX, $e.Bounds.Y, ($e.Bounds.Right - $textX), $e.Bounds.Height)
        $textFlags = [System.Windows.Forms.TextFormatFlags]::Left -bor `
            [System.Windows.Forms.TextFormatFlags]::VerticalCenter -bor `
            [System.Windows.Forms.TextFormatFlags]::NoPrefix -bor `
            [System.Windows.Forms.TextFormatFlags]::EndEllipsis
        [System.Windows.Forms.TextRenderer]::DrawText(
            $e.Graphics, [string]$sender.Items[$e.Index], $sender.Font, $textRect, $Paper, $rowBack, $textFlags)
    })
    $list
}

$surveyList = New-PhosphorCheckList -Parent $pageSurvey -X $PadX -Y $y -Width $ContentW -RowCount 11
$script:GameKeys = @()
$script:CatalogLoaded = $false
$y = $surveyList.Parent.Bottom + (S 4)
$lblSurveyStatus = New-UiLabel -Parent $pageSurvey -Text "Still looking for installed games..." -Font $FontSub -Color $Mist -X $PadX -Y $y -Width $ContentW -Height (S 16)
$y = $lblSurveyStatus.Bottom + (S 10)

New-Eyebrow -Parent $pageSurvey -Text "Your display" -Y $y | Out-Null
$y += S 20

# Same phosphor check rows as the game list - one check language per page.
# Row indices: 0 = HDR, 1 = VRR, 2 = capture/streaming.
$displayList = New-PhosphorCheckList -Parent $pageSurvey -X $PadX -Y $y -Width $ContentW -RowCount 3
foreach ($displayRow in @(
    "My monitor supports HDR and I use it",
    "My monitor has G-SYNC / FreeSync (VRR) turned on",
    "I stream or record gameplay (OBS, Medal, ...)")) {
    $displayList.Items.Add($displayRow) | Out-Null
    $displayList.Tag.Checked.Add($false) | Out-Null
}
$y = $displayList.Parent.Bottom + (S 12)
New-UiLabel -Parent $pageSurvey -Text "Best guesses are pre-filled from your hardware. Nothing here is permanent - re-run setup or hide profiles from the tray anytime." -Font $FontSub -Color $Mist -X $PadX -Y $y -Width $ContentW | Out-Null

$btnFinishSetup = New-InstallerButton -Parent $pageSurvey -Text "Finish setup" -X ($PadX + $ContentW - (S 132)) -Y $buttonY -Width (S 132) -Primary $true
$btnBack = New-InstallerButton -Parent $pageSurvey -Text "Back" -X ($PadX + $ContentW - (S 132) - (S 10) - (S 92)) -Y $buttonY -Width (S 92) -Primary $false

$btnNext.Add_Click({
    Show-Page $pageSurvey
    $form.AcceptButton = $btnFinishSetup
})
$btnBack.Add_Click({
    Show-Page $pageOptions
    $form.AcceptButton = $btnNext
})

# --- progress page ---------------------------------------------------------
$lblProgressHead = New-UiLabel -Parent $pageProgress -Text "Setting up..." -Font $FontHeading -Color $Paper -X $PadX -Y (S 6) -Width $ContentW
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
$lblDoneUndo = New-UiLabel -Parent $pageDone -Text "Changed your mind later? Uninstall from Windows Settings, or run 'computa uninstall' - the snapshot from today puts everything back the way it was." -Font $FontSub -Color $Mist -X $PadX -Y ($lblDonePath.Bottom + (S 4)) -Width $ContentW

$doneButtonY = $pageH - (S 52)
$btnOpenTray = New-InstallerButton -Parent $pageDone -Text "Open the tray now" -X ($PadX + $ContentW - (S 170)) -Y $doneButtonY -Width (S 170) -Primary $true
$btnClose = New-InstallerButton -Parent $pageDone -Text "Close" -X ($PadX + $ContentW - (S 170) - (S 10) - (S 92)) -Y $doneButtonY -Width (S 92) -Primary $false
$btnClose.Add_Click({ $form.Close() })
$btnOpenTray.Add_Click({
    try {
        Start-Process -FilePath $BackendExe -ArgumentList "tray" -WindowStyle Hidden
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
    if ($lines.Count -eq 0) { $lines = @("Couldn't inspect this PC - that's okay, setup continues normally.") }
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

    if ($Plan.game_catalog -and $Plan.game_catalog.Count -gt 0) {
        $surveyList.Items.Clear()
        $surveyList.Tag.Checked.Clear()
        $script:GameKeys = @()
        foreach ($entry in $Plan.game_catalog) {
            $surveyList.Items.Add($entry.name) | Out-Null
            $surveyList.Tag.Checked.Add([bool]$entry.detected) | Out-Null
            $script:GameKeys += $entry.key
        }
        $surveyList.Invalidate()
        $script:CatalogLoaded = $true
        $detectedCount = @($Plan.game_catalog | Where-Object { $_.detected }).Count
        if ($detectedCount -gt 0) {
            $lblSurveyStatus.Text = "Found $detectedCount of these installed - pre-checked for you."
        }
        else {
            $lblSurveyStatus.Text = "No installed games spotted - check whatever you play."
        }
    }
    else {
        $lblSurveyStatus.Text = "Couldn't scan this PC for games - the tray will show the full profile list."
    }
    if ($Plan.hdr_capable -eq $true) { $displayList.Tag.Checked[0] = $true }
    if ($Plan.vrr_capable -eq $true) { $displayList.Tag.Checked[1] = $true }
    $displayList.Invalidate()
}

function Start-PlanProbe {
    param([string]$ProbeExe)
    $script:PlanOut = [System.IO.Path]::GetTempFileName()
    $script:PlanErr = [System.IO.Path]::GetTempFileName()
    try {
        # Both streams redirected: launched from wscript there is no console
        # anywhere in the process tree for stderr to inherit.
        $script:PlanProc = Start-Process -FilePath $ProbeExe -ArgumentList "setup", "--plan" `
            -RedirectStandardOutput $script:PlanOut -RedirectStandardError $script:PlanErr `
            -WindowStyle Hidden -PassThru
    }
    catch {
        $lblHardware.Text = "Couldn't inspect this PC - that's okay, setup continues normally."
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
                $lblHardware.Text = "Couldn't inspect this PC - that's okay, setup continues normally."
            }
            return
        }
        $script:PlanTimer.Stop()
        try {
            $raw = [System.IO.File]::ReadAllText($script:PlanOut).Trim()
            if ($raw) { Apply-PlanToUi (ConvertFrom-Json ($raw -split "`n")[0]) }
            else { $lblHardware.Text = "Couldn't inspect this PC - that's okay, setup continues normally." }
        }
        catch {
            $lblHardware.Text = "Couldn't inspect this PC - that's okay, setup continues normally."
        }
    })
    $script:PlanTimer.Start()
}

# --- setup execution -------------------------------------------------------
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
        $bullets = @()
        if ($done.summary) { foreach ($item in $done.summary) { $bullets += "$GlyphBullet $item" } }
        if ($bullets.Count -eq 0) { $bullets += "$GlyphBullet Setup finished" }
        $bullets += " "
        $bullets += "Open the tray, pick the profile for your game, and computa handles the rest."
        $lblDoneBody.Text = $bullets -join "`n"
        if ($done.needs_reboot) {
            $lblDoneReboot.Text = "One thing to know: a restart is needed to finish ($($done.reboot_reasons -join ', ')). No rush - Windows will pick it up on your next reboot."
        }
        $lblDonePath.Text = "Installed at: $script:InstallRoot"
        $btnOpenTray.Visible = $true
    }
    else {
        $lblDoneHead.Text = "Something didn't finish."
        $lines = @()
        if ($script:StepErrors.Count -gt 0) { $lines += $script:StepErrors }
        elseif ($null -eq $done) { $lines += "The setup process ended unexpectedly." }
        $lines += " "
        $lines += "Everything that did finish is safe, and nothing else on your PC was changed. You can run setup again from the Start Menu, or ask the friend who sent you this to take a look."
        $lblDoneBody.Text = $lines -join "`n"
        $lblDoneHead.ForeColor = $Danger
        $lblDoneUndo.Visible = $false
        $lblDonePath.Visible = $false
        $btnOpenTray.Visible = $false
    }
    Show-Page $pageDone
}

function Start-Setup {
    $btnFinishSetup.Enabled = $false
    $btnBack.Enabled = $false

    $backendArgs = @("setup", "--unattended")
    if ($rowSnapshot.Check.Checked) { $backendArgs += "--baseline" } else { $backendArgs += "--no-baseline" }
    $backendArgs += "--config"
    if ($rowTray.Check.Checked) { $backendArgs += "--tray-autostart" } else { $backendArgs += "--no-tray-autostart" }
    if ($rowKb.Check.Visible -and $rowKb.Check.Checked) {
        foreach ($kbId in $script:PlanKbIds) { $backendArgs += @("--remove-kb", $kbId) }
    }

    # Survey answers: only filter when the catalog loaded and the user
    # actually picked games; unchecked-everything means keep the full list.
    $gameChecked = $surveyList.Tag.Checked
    $checkedIndices = @()
    for ($index = 0; $index -lt $gameChecked.Count; $index++) {
        if ($gameChecked[$index]) { $checkedIndices += $index }
    }
    if ($script:CatalogLoaded -and $checkedIndices.Count -gt 0) {
        foreach ($index in $checkedIndices) {
            $backendArgs += @("--game", $script:GameKeys[$index])
        }
        if ($displayList.Tag.Checked[0]) { $backendArgs += "--hdr" } else { $backendArgs += "--no-hdr" }
        if ($displayList.Tag.Checked[1]) { $backendArgs += "--vrr" } else { $backendArgs += "--no-vrr" }
        if ($displayList.Tag.Checked[2]) { $backendArgs += "--capture" } else { $backendArgs += "--no-capture" }
    }

    $script:OutOffset = 0
    $script:OutPartial = ""
    $script:DoneEvent = $null
    $script:InstallOut = [System.IO.Path]::GetTempFileName()
    $script:InstallErr = [System.IO.Path]::GetTempFileName()
    try {
        $script:InstallProc = Start-Process -FilePath $BackendExe -ArgumentList $backendArgs `
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

$btnFinishSetup.Add_Click({
    try { Start-Setup }
    catch {
        [System.Windows.Forms.MessageBox]::Show(
            "Setup couldn't start:`n$($_.Exception.Message)",
            "computa setup",
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Warning) | Out-Null
        $btnFinishSetup.Enabled = $true
        $btnBack.Enabled = $true
    }
})

# --- preview mode (screenshot harness; canned data, changes nothing) -------
if ($previewMode) {
    $cannedPlan = @'
{"app_version":"1.1.0","is_admin":true,
 "hardware":{"gpu":"NVIDIA GeForce RTX 3080","cpu":"Intel(R) Core(TM) i7-12700K","ram_gb":32.0,"monitor":"Generic PnP Monitor @ 165Hz","monitor_count":2},
 "gpu_vendor":"nvidia","gpu_vendor_note":"NVIDIA GPU - full driver tuning available.",
 "problematic_kbs":[{"kb_id":"KB5074109","title":"Reported NVIDIA FPS regression","affected":"NVIDIA GPUs - reported FPS drops (impact varies by system)."}],
 "detected_games":[{"profile":"counter-strike-2","games":["Counter-Strike 2"]},{"profile":"fortnite","games":["Fortnite"]}],
 "hdr_capable":true,"vrr_capable":true,
 "game_catalog":[
  {"key":"slippi-melee","name":"Super Smash Bros. Melee (Slippi)","category":"Fighting","detected":false},
  {"key":"rivals2","name":"Rivals 2","category":"Fighting","detected":false},
  {"key":"diablo4","name":"Diablo 4","category":"RPGs","detected":false},
  {"key":"fortnite","name":"Fortnite","category":"Shooters","detected":true},
  {"key":"marvel-rivals","name":"Marvel Rivals","category":"Shooters","detected":false},
  {"key":"deadlock","name":"Deadlock","category":"Shooters","detected":false},
  {"key":"counter-strike-2","name":"Counter-Strike 2","category":"Shooters","detected":true},
  {"key":"overwatch2","name":"Overwatch 2","category":"Shooters","detected":false},
  {"key":"pokemon-auto-chess","name":"Pokemon Auto Chess","category":"Other","detected":false},
  {"key":"pacdeluxe","name":"PACDeluxe (Pokemon Auto Chess)","category":"Other","detected":false},
  {"key":"ryujinx-ssbu","name":"SSBU / HewDraw Remix (Ryujinx)","category":"Fighting","detected":false}]}
'@
    switch ($PreviewUi) {
        "options" {
            Apply-PlanToUi (ConvertFrom-Json $cannedPlan)
            Show-Page $pageOptions
        }
        "survey" {
            Apply-PlanToUi (ConvertFrom-Json $cannedPlan)
            Show-Page $pageSurvey
        }
        "progress" {
            Add-StepRow -Id "tray_assets" -Label "Putting the tray helper's files in place"
            Add-StepRow -Id "config" -Label "Creating your settings file"
            Add-StepRow -Id "baseline" -Label "Saving a snapshot of your current settings"
            Add-StepRow -Id "preferences" -Label "Tuning the tray to your games"
            Add-StepRow -Id "state" -Label "Finishing up"
            Update-StepRow -Id "tray_assets" -Status "ok"
            Update-StepRow -Id "config" -Status "ok"
            Update-StepRow -Id "baseline" -Status "running"
            Show-Page $pageProgress
        }
        "done" {
            $script:DoneEvent = ConvertFrom-Json '{"event":"done","success":true,"needs_reboot":false,"reboot_reasons":[],"baseline_backup_id":"2026-07-20_120000","summary":["Settings file created","Safety snapshot saved (2026-07-20_120000)","Tray tuned to your games (3 selected)","Tray will start with Windows"]}'
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
$form.Add_Shown({ Start-PlanProbe -ProbeExe $BackendExe })
[System.Windows.Forms.Application]::Run($form)
