# ABSO-Settings.ps1 - Settings panel and config persistence for A.B.S.O. tray

$script:ConfigDir = Join-Path $env:APPDATA "ABSO"
$script:ConfigFile = Join-Path $script:ConfigDir "tray-config.json"
$script:SettingsForm = $null

# ============================================================================
# CONFIG MANAGEMENT
# ============================================================================

function Get-DefaultConfig {
    <#
    .SYNOPSIS
    Returns the default configuration hashtable.
    #>
    return @{
        favorites       = @()
        defaultProfile  = $null
        soundVolume     = 0.2
        soundEnabled    = $true
        hotkeys         = @{
            openMenu = "Ctrl+Shift+A"
            restore  = "Ctrl+Shift+R"
        }
        showQuickPanel  = $false
        animationSpeed  = "normal"
        recentProfiles  = @()
        profileHistory  = @()
    }
}

function Read-TrayConfig {
    <#
    .SYNOPSIS
    Reads the tray config from disk, creating defaults if missing or corrupt.
    #>
    $defaults = Get-DefaultConfig

    if (-not (Test-Path $script:ConfigDir)) {
        New-Item -Path $script:ConfigDir -ItemType Directory -Force -ErrorAction SilentlyContinue | Out-Null
    }

    if (Test-Path $script:ConfigFile) {
        try {
            $json = Get-Content $script:ConfigFile -Raw -ErrorAction Stop | ConvertFrom-Json
            $config = @{}

            # Merge with defaults (backward compatibility)
            foreach ($key in $defaults.Keys) {
                if ($null -ne $json.$key) {
                    $val = $json.$key
                    # Convert PSCustomObject arrays to proper arrays
                    if ($val -is [System.Object[]]) {
                        $config[$key] = @($val)
                    }
                    elseif ($val -is [PSCustomObject]) {
                        $ht = @{}
                        $val.PSObject.Properties | ForEach-Object { $ht[$_.Name] = $_.Value }
                        $config[$key] = $ht
                    }
                    else {
                        $config[$key] = $val
                    }
                }
                else {
                    $config[$key] = $defaults[$key]
                }
            }
            return $config
        }
        catch {
            # Corrupt config - back up corrupt file, then reset to defaults
            # Clean old corrupt backups first (keep at most 3)
            try {
                $corruptFiles = Get-ChildItem -Path $script:ConfigDir -Filter "tray-config.json.corrupt.*" -ErrorAction SilentlyContinue |
                    Sort-Object LastWriteTime -Descending |
                    Select-Object -Skip 2
                foreach ($old in $corruptFiles) {
                    Remove-Item $old.FullName -Force -ErrorAction SilentlyContinue
                }
            } catch {}
            $backupPath = "$($script:ConfigFile).corrupt.$(Get-Date -Format 'yyyyMMdd-HHmmss')"
            try {
                Copy-Item $script:ConfigFile $backupPath -Force -ErrorAction SilentlyContinue
            } catch {}
            Write-Warning "ABSO: Corrupt config backed up to $backupPath, resetting to defaults"
        }
    }

    # Write defaults
    Save-TrayConfig $defaults
    return $defaults
}

function Save-TrayConfig {
    <#
    .SYNOPSIS
    Saves the tray config to disk.
    #>
    param([hashtable]$Config)

    if (-not (Test-Path $script:ConfigDir)) {
        New-Item -Path $script:ConfigDir -ItemType Directory -Force -ErrorAction SilentlyContinue | Out-Null
    }

    try {
        $Config | ConvertTo-Json -Depth 4 | Set-Content $script:ConfigFile -Force -ErrorAction Stop
    }
    catch {
        $errMsg = "Failed to save config: $($_.Exception.Message)"
        Write-Warning "ABSO: $errMsg"
        # Write to log if available (function may be called before log is set up)
        if (Get-Command Write-TrayLog -ErrorAction SilentlyContinue) {
            Write-TrayLog $errMsg -Level "ERROR"
        }
    }
}

# ============================================================================
# FAVORITES
# ============================================================================

function Test-Favorite {
    <#
    .SYNOPSIS
    Checks if a profile ID is in the favorites list.
    #>
    param([string]$ProfileId, [hashtable]$Config)
    return ($Config.favorites -contains $ProfileId)
}

function Toggle-Favorite {
    <#
    .SYNOPSIS
    Adds or removes a profile from favorites.
    #>
    param([string]$ProfileId, [hashtable]$Config)

    if ($Config.favorites -contains $ProfileId) {
        $Config.favorites = @($Config.favorites | Where-Object { $_ -ne $ProfileId })
    }
    else {
        $Config.favorites = @($Config.favorites) + $ProfileId
    }
    Save-TrayConfig $Config
    return $Config
}

# ============================================================================
# PROFILE HISTORY
# ============================================================================

function Add-ProfileHistory {
    <#
    .SYNOPSIS
    Records a profile application in history.
    #>
    param([string]$ProfileId, [string]$ProfileName, [hashtable]$Config)

    $entry = @{
        id        = $ProfileId
        name      = $ProfileName
        timestamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    }

    # Add to recent (max 10)
    $recent = @($Config.recentProfiles)
    # Remove duplicates of same profile
    $recent = @($recent | Where-Object { $_.id -ne $ProfileId })
    $recent = @($entry) + $recent
    if ($recent.Count -gt 10) {
        $recent = $recent[0..9]
    }
    $Config.recentProfiles = $recent

    # Add to full history (max 50)
    $history = @($Config.profileHistory)
    $history = @($entry) + $history
    if ($history.Count -gt 50) {
        $history = $history[0..49]
    }
    $Config.profileHistory = $history

    Save-TrayConfig $Config
    return $Config
}

# ============================================================================
# SETTINGS PANEL
# ============================================================================

function Show-SettingsPanel {
    <#
    .SYNOPSIS
    Shows a floating settings window (non-modal).
    .PARAMETER Config
    The current config hashtable.
    .PARAMETER OnSave
    Scriptblock to call when settings are saved, receives updated config.
    #>
    param(
        [hashtable]$Config,
        [scriptblock]$OnSave
    )

    if ($script:SettingsForm -and -not $script:SettingsForm.IsDisposed) {
        $script:SettingsForm.BringToFront()
        return
    }

    $form = New-Object System.Windows.Forms.Form
    $form.Text = "A.B.S.O. Settings"
    $form.Size = New-Object System.Drawing.Size(400, 420)
    $form.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::FixedDialog
    $form.MaximizeBox = $false
    $form.StartPosition = [System.Windows.Forms.FormStartPosition]::CenterScreen
    $form.BackColor = [System.Drawing.Color]::FromArgb(255, 32, 32, 36)
    $form.ForeColor = [System.Drawing.Color]::FromArgb(255, 220, 220, 220)
    $form.Font = New-Object System.Drawing.Font("Segoe UI", 9)
    $form.TopMost = $true

    $y = 16

    # --- General Section ---
    $genLabel = New-Object System.Windows.Forms.Label
    $genLabel.Text = "GENERAL"
    $genLabel.ForeColor = [System.Drawing.Color]::FromArgb(255, 220, 180, 70)
    $genLabel.Font = New-Object System.Drawing.Font("Segoe UI", 9, [System.Drawing.FontStyle]::Bold)
    $genLabel.Location = New-Object System.Drawing.Point(16, $y)
    $genLabel.AutoSize = $true
    $form.Controls.Add($genLabel)
    $y += 28

    # Default profile
    $defLabel = New-Object System.Windows.Forms.Label
    $defLabel.Text = "Default Profile (apply on startup):"
    $defLabel.Location = New-Object System.Drawing.Point(16, $y)
    $defLabel.AutoSize = $true
    $form.Controls.Add($defLabel)
    $y += 24

    $defCombo = New-Object System.Windows.Forms.ComboBox
    $defCombo.Location = New-Object System.Drawing.Point(16, $y)
    $defCombo.Size = New-Object System.Drawing.Size(350, 28)
    $defCombo.DropDownStyle = [System.Windows.Forms.ComboBoxStyle]::DropDownList
    $defCombo.BackColor = [System.Drawing.Color]::FromArgb(255, 50, 50, 55)
    $defCombo.ForeColor = [System.Drawing.Color]::FromArgb(255, 220, 220, 220)
    $defCombo.Items.Add("(None)") | Out-Null
    # Populate with available profiles
    if ($script:Profiles) {
        foreach ($id in $script:Profiles.Keys) {
            $p = $script:Profiles[$id]
            $defCombo.Items.Add("$id - $($p.Name)") | Out-Null
        }
    }
    # Select current default
    $defCombo.SelectedIndex = 0
    if ($Config.defaultProfile) {
        for ($i = 1; $i -lt $defCombo.Items.Count; $i++) {
            if ($defCombo.Items[$i].ToString().StartsWith("$($Config.defaultProfile) -")) {
                $defCombo.SelectedIndex = $i
                break
            }
        }
    }
    $form.Controls.Add($defCombo)
    $y += 36

    # --- Audio Section ---
    $audioLabel = New-Object System.Windows.Forms.Label
    $audioLabel.Text = "AUDIO"
    $audioLabel.ForeColor = [System.Drawing.Color]::FromArgb(255, 220, 180, 70)
    $audioLabel.Font = New-Object System.Drawing.Font("Segoe UI", 9, [System.Drawing.FontStyle]::Bold)
    $audioLabel.Location = New-Object System.Drawing.Point(16, $y)
    $audioLabel.AutoSize = $true
    $form.Controls.Add($audioLabel)
    $y += 28

    $soundCheck = New-Object System.Windows.Forms.CheckBox
    $soundCheck.Text = "Enable sound effects"
    $soundCheck.Checked = $Config.soundEnabled
    $soundCheck.Location = New-Object System.Drawing.Point(16, $y)
    $soundCheck.ForeColor = [System.Drawing.Color]::FromArgb(255, 220, 220, 220)
    $soundCheck.AutoSize = $true
    $form.Controls.Add($soundCheck)
    $y += 28

    $volLabel = New-Object System.Windows.Forms.Label
    $volLabel.Text = "Volume:"
    $volLabel.Location = New-Object System.Drawing.Point(16, ($y + 2))
    $volLabel.AutoSize = $true
    $form.Controls.Add($volLabel)

    $volTrack = New-Object System.Windows.Forms.TrackBar
    $volTrack.Location = New-Object System.Drawing.Point(80, $y)
    $volTrack.Size = New-Object System.Drawing.Size(200, 30)
    $volTrack.Minimum = 0
    $volTrack.Maximum = 100
    $volTrack.Value = [int]($Config.soundVolume * 100)
    $volTrack.TickFrequency = 25
    $volTrack.BackColor = [System.Drawing.Color]::FromArgb(255, 32, 32, 36)
    $form.Controls.Add($volTrack)

    $volValueLabel = New-Object System.Windows.Forms.Label
    $volValueLabel.Text = "$([int]($Config.soundVolume * 100))%"
    $volValueLabel.Location = New-Object System.Drawing.Point(290, ($y + 2))
    $volValueLabel.AutoSize = $true
    $form.Controls.Add($volValueLabel)

    $volTrack.Add_ValueChanged({
        $volValueLabel.Text = "$($volTrack.Value)%"
    })
    $y += 48

    # --- Hotkeys Section ---
    $hkLabel = New-Object System.Windows.Forms.Label
    $hkLabel.Text = "HOTKEYS"
    $hkLabel.ForeColor = [System.Drawing.Color]::FromArgb(255, 220, 180, 70)
    $hkLabel.Font = New-Object System.Drawing.Font("Segoe UI", 9, [System.Drawing.FontStyle]::Bold)
    $hkLabel.Location = New-Object System.Drawing.Point(16, $y)
    $hkLabel.AutoSize = $true
    $form.Controls.Add($hkLabel)
    $y += 28

    $hk1Label = New-Object System.Windows.Forms.Label
    $hk1Label.Text = "Open Menu:"
    $hk1Label.Location = New-Object System.Drawing.Point(16, ($y + 4))
    $hk1Label.AutoSize = $true
    $form.Controls.Add($hk1Label)

    $hk1Text = New-Object System.Windows.Forms.TextBox
    $hk1Text.Text = $Config.hotkeys.openMenu
    $hk1Text.Location = New-Object System.Drawing.Point(120, $y)
    $hk1Text.Size = New-Object System.Drawing.Size(200, 26)
    $hk1Text.BackColor = [System.Drawing.Color]::FromArgb(255, 50, 50, 55)
    $hk1Text.ForeColor = [System.Drawing.Color]::FromArgb(255, 220, 220, 220)
    $hk1Text.ReadOnly = $true
    $form.Controls.Add($hk1Text)
    $y += 32

    $hk2Label = New-Object System.Windows.Forms.Label
    $hk2Label.Text = "Restore:"
    $hk2Label.Location = New-Object System.Drawing.Point(16, ($y + 4))
    $hk2Label.AutoSize = $true
    $form.Controls.Add($hk2Label)

    $hk2Text = New-Object System.Windows.Forms.TextBox
    $hk2Text.Text = $Config.hotkeys.restore
    $hk2Text.Location = New-Object System.Drawing.Point(120, $y)
    $hk2Text.Size = New-Object System.Drawing.Size(200, 26)
    $hk2Text.BackColor = [System.Drawing.Color]::FromArgb(255, 50, 50, 55)
    $hk2Text.ForeColor = [System.Drawing.Color]::FromArgb(255, 220, 220, 220)
    $hk2Text.ReadOnly = $true
    $form.Controls.Add($hk2Text)
    $y += 48

    # --- Save / Close Buttons ---
    $saveBtn = New-Object System.Windows.Forms.Button
    $saveBtn.Text = "Save"
    $saveBtn.Location = New-Object System.Drawing.Point(200, ($y + 10))
    $saveBtn.Size = New-Object System.Drawing.Size(80, 32)
    $saveBtn.BackColor = [System.Drawing.Color]::FromArgb(255, 90, 200, 120)
    $saveBtn.ForeColor = [System.Drawing.Color]::FromArgb(255, 20, 20, 20)
    $saveBtn.FlatStyle = [System.Windows.Forms.FlatStyle]::Flat
    $saveBtn.Font = New-Object System.Drawing.Font("Segoe UI", 9, [System.Drawing.FontStyle]::Bold)
    $saveBtn.Add_Click({
        $Config.soundEnabled = $soundCheck.Checked
        $Config.soundVolume = $volTrack.Value / 100.0
        # Save default profile selection
        if ($defCombo.SelectedIndex -le 0) {
            $Config.defaultProfile = $null
        } else {
            $selected = $defCombo.SelectedItem.ToString()
            $Config.defaultProfile = ($selected -split ' - ', 2)[0]
        }
        Save-TrayConfig $Config
        if ($OnSave) { & $OnSave $Config }
        $form.Close()
    })
    $form.Controls.Add($saveBtn)

    $closeBtn = New-Object System.Windows.Forms.Button
    $closeBtn.Text = "Close"
    $closeBtn.Location = New-Object System.Drawing.Point(290, ($y + 10))
    $closeBtn.Size = New-Object System.Drawing.Size(80, 32)
    $closeBtn.BackColor = [System.Drawing.Color]::FromArgb(255, 60, 60, 65)
    $closeBtn.ForeColor = [System.Drawing.Color]::FromArgb(255, 200, 200, 200)
    $closeBtn.FlatStyle = [System.Windows.Forms.FlatStyle]::Flat
    $closeBtn.Add_Click({ $form.Close() })
    $form.Controls.Add($closeBtn)

    $script:SettingsForm = $form
    $form.Add_FormClosed({
        $form.Dispose()
        $script:SettingsForm = $null
    })
    $form.Show()
}

# ============================================================================
# GLOBAL HOTKEYS (Win32 API)
# ============================================================================

$script:HotkeysRegistered = $false
$script:HotkeyActions = @{}

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;

public class HotkeyHelper {
    [DllImport("user32.dll")]
    public static extern bool RegisterHotKey(IntPtr hWnd, int id, uint fsModifiers, uint vk);

    [DllImport("user32.dll")]
    public static extern bool UnregisterHotKey(IntPtr hWnd, int id);

    public const uint MOD_ALT = 0x0001;
    public const uint MOD_CONTROL = 0x0002;
    public const uint MOD_SHIFT = 0x0004;
    public const uint MOD_WIN = 0x0008;
    public const uint MOD_NOREPEAT = 0x4000;
}
"@ -ErrorAction SilentlyContinue

function Parse-HotkeyString {
    <#
    .SYNOPSIS
    Parses a hotkey string like "Ctrl+Shift+A" into modifier flags and virtual key code.
    #>
    param([string]$HotkeyStr)

    $parts = $HotkeyStr -split '\+'
    $modifiers = [uint32]0
    $vk = [uint32]0

    foreach ($part in $parts) {
        $p = $part.Trim()
        switch ($p.ToLower()) {
            "ctrl"  { $modifiers = $modifiers -bor 0x0002 }
            "alt"   { $modifiers = $modifiers -bor 0x0001 }
            "shift" { $modifiers = $modifiers -bor 0x0004 }
            "win"   { $modifiers = $modifiers -bor 0x0008 }
            default {
                if ($p.Length -eq 1) {
                    $vk = [uint32][char]$p.ToUpper()
                }
                elseif ($p -match '^F(\d+)$') {
                    $vk = [uint32](0x70 + [int]$Matches[1] - 1)
                }
                elseif ($p -match '^\d$') {
                    $vk = [uint32][char]$p
                }
            }
        }
    }

    # Add MOD_NOREPEAT
    $modifiers = $modifiers -bor 0x4000

    return @{ Modifiers = $modifiers; VK = $vk }
}

function Register-GlobalHotkeys {
    <#
    .SYNOPSIS
    Registers global hotkeys based on config.
    .PARAMETER WindowHandle
    The hidden form's window handle for receiving WM_HOTKEY.
    .PARAMETER Config
    Config hashtable with hotkeys section.
    .PARAMETER Actions
    Hashtable mapping hotkey names to scriptblocks.
    #>
    param(
        [IntPtr]$WindowHandle,
        [hashtable]$Config,
        [hashtable]$Actions
    )

    $id = 1
    foreach ($name in $Config.hotkeys.Keys) {
        $hkStr = $Config.hotkeys[$name]
        if (-not $hkStr) { continue }

        $parsed = Parse-HotkeyString $hkStr
        if ($parsed.VK -gt 0) {
            $result = [HotkeyHelper]::RegisterHotKey($WindowHandle, $id, $parsed.Modifiers, $parsed.VK)
            if ($result) {
                $script:HotkeyActions[$id] = $Actions[$name]
            }
            $id++
        }
    }
    $script:HotkeysRegistered = $true
}

function Unregister-GlobalHotkeys {
    <#
    .SYNOPSIS
    Unregisters all global hotkeys.
    #>
    param([IntPtr]$WindowHandle)

    if ($script:HotkeysRegistered) {
        foreach ($id in $script:HotkeyActions.Keys) {
            [HotkeyHelper]::UnregisterHotKey($WindowHandle, $id) | Out-Null
        }
        $script:HotkeyActions = @{}
        $script:HotkeysRegistered = $false
    }
}

function Get-HotkeyAction {
    <#
    .SYNOPSIS
    Gets the action scriptblock for a hotkey ID.
    #>
    param([int]$HotkeyId)
    if ($script:HotkeyActions.ContainsKey($HotkeyId)) {
        return $script:HotkeyActions[$HotkeyId]
    }
    return $null
}
