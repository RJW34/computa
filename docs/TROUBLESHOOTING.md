# A.B.S.O. Troubleshooting Guide

**Adaptive Battle Station Optimizer**

This guide helps diagnose and resolve common issues with A.B.S.O.

## Table of Contents

- [Installation Issues](#installation-issues)
- [Permission Errors](#permission-errors)
- [Detection Problems](#detection-problems)
- [Reboot Requirements When Switching Profiles](#reboot-requirements-when-switching-profiles)
- [Profile Application Failures](#profile-application-failures)
- [Backup and Restore Issues](#backup-and-restore-issues)
- [Performance Issues](#performance-issues)
- [Recovery Procedures](#recovery-procedures)
- [Getting Help](#getting-help)

---

## Installation Issues

### Missing Dependencies

**Symptom:** `ModuleNotFoundError: No module named 'wmi'` or similar

**Solution:**
```bash
pip install -r requirements.txt
```

If you're using a virtual environment, make sure it's activated:
```bash
venv\Scripts\activate
pip install -r requirements.txt
```

### pywin32 Installation Fails

**Symptom:** Error during `pip install pywin32`

**Solution:**
1. Install from prebuilt wheel:
   ```bash
   pip install pywin32 --no-cache-dir
   ```

2. If that fails, download from [GitHub releases](https://github.com/mhammond/pywin32/releases)

3. Run post-install script:
   ```bash
   python Scripts/pywin32_postinstall.py -install
   ```

### WMI Module Not Working

**Symptom:** `WMI module not available` warning

**Solution:**
1. Ensure pywin32 is installed correctly
2. Run Python as Administrator once to initialize WMI properly
3. Restart your terminal/IDE

---

## Permission Errors

> **Note:** A.B.S.O. requires administrator privileges for most operations.

### "Access Denied" or "Requires Administrator"

**Symptom:** Operations fail with permission errors

**Solution:**
1. **Run as Administrator:**
   - Right-click Command Prompt or PowerShell
   - Select "Run as administrator"
   - Navigate to project directory
   - Run A.B.S.O.

2. **Or use the elevation prompt:**
   A.B.S.O. will offer to re-launch with admin privileges if needed.

### Registry Access Denied

**Symptom:** `RegistryWriteError: Permission denied`

**Cause:** Some registry keys require SYSTEM-level access

**Solution:**
1. Run as Administrator
2. Some keys (like HAGS) may require a Group Policy exception
3. Check if antivirus is blocking registry access

### Cannot Modify Power Settings

**Symptom:** Power plan changes fail

**Solution:**
1. Run as Administrator
2. Check if your organization has Group Policy restrictions
3. Try manually in Control Panel to verify you have permission

---

## Detection Problems

### GPU Not Detected

**Symptom:** GPU shows as `None` or "Unknown"

**Causes and Solutions:**

1. **nvidia-smi not in PATH:**
   ```bash
   # Add Nvidia tools to PATH
   set PATH=%PATH%;C:\Program Files\NVIDIA Corporation\NVSMI
   ```

2. **AMD GPU:** Currently optimized for Nvidia GPUs. WMI fallback should detect AMD cards.

3. **Integrated Graphics:** Intel/AMD integrated graphics may show minimal info.

4. **Driver Issues:** Update your GPU driver.

### Monitor VRR Not Detected

**Symptom:** `vrr_supported: unknown` even on VRR-capable monitor

**Causes:**
- Monitor doesn't expose VRR in EDID data
- DisplayPort/HDMI doesn't support VRR signaling
- Older monitor firmware

**Solution:**
1. Check Nvidia Control Panel or AMD Adrenalin for VRR status
2. Manually verify G-Sync/FreeSync is enabled
3. Update monitor firmware if available

### CPU Detection Fails

**Symptom:** CPU info is `None`

**Solution:**
1. Verify WMI service is running:
   ```bash
   sc query winmgmt
   ```
2. Restart WMI service:
   ```bash
   net stop winmgmt && net start winmgmt
   ```

---

## Reboot Requirements When Switching Profiles

### Understanding When Reboots Are Actually Needed

A.B.S.O. may report "reboot required" after applying a profile, but **you don't always need to reboot**. Here's when you actually need to:

**Reboot IS required:**
- First time applying a profile that includes Memory or MPO settings
- After Windows updates that reset registry values
- When switching FROM a profile that doesn't use certain handlers TO one that does

**Reboot is NOT required:**
- Re-applying the same profile (values already correct)
- Switching between profiles that share the same reboot-requiring settings
- Switching from Diablo 4 → Rivals 2 (if you've applied Rivals 2 before and rebooted)

### Why This Works

Settings like Memory Management (DisablePagingExecutive) and MPO are stored in the registry. Once set and rebooted:
- The kernel reads the values at boot time
- Writing the same value again doesn't change kernel behavior
- No reboot needed because the settings are already active

### Profile Comparison

| Switching From | Switching To | Reboot Needed? |
|----------------|--------------|----------------|
| Fresh Windows | Rivals 2 | **Yes** (first time) |
| Rivals 2 | Diablo 4 | No (Diablo 4 doesn't use Memory/MPO) |
| Diablo 4 | Rivals 2 | No (if Rivals 2 was applied before) |
| Rivals 2 | Rivals 2 | No (same settings) |
| Slippi Melee | Rivals 2 | No (both use similar settings) |

### What If I'm Unsure?

If you're uncertain whether a reboot is needed:
1. Apply the profile
2. Run the game and test
3. If optimizations don't seem active, then reboot
4. After that first reboot, subsequent profile switches won't need rebooting

---

## Profile Application Failures

### "Unknown profile" Error

**Symptom:** `ProfileNotFoundError: Unknown profile: xyz`

**Solution:**
List available profiles:
```bash
python -m abso profiles
```

Use the exact profile ID (e.g., `slippi-melee`, not `Slippi Melee`).

### Partial Application Failure

**Symptom:** Some settings applied, others failed

**Diagnosis:**
```python
result = applier.apply_profile("profile-name")
print(f"Applied: {result.applied_settings}")
print(f"Failed: {result.failed_settings}")
```

**Common Causes:**
1. **Permission issues:** Run as Administrator
2. **Missing dependencies:** Check Nvidia Profile Inspector is installed
3. **Antivirus blocking:** Add exception for A.B.S.O.

### Nvidia Settings Not Applied

**Symptom:** Nvidia optimizations fail

**Solutions:**
1. Install [Nvidia Profile Inspector](https://github.com/Orbmu2k/nvidiaProfileInspector/releases)
2. Place `nvidiaProfileInspector.exe` in system PATH or A.B.S.O. directory
3. Ensure Nvidia driver is up to date
4. Close any Nvidia applications during apply

### Network Settings Fail

**Symptom:** TCP optimization fails

**Solutions:**
1. Run as Administrator
2. Check Windows Firewall isn't blocking netsh
3. Verify network adapter is active:
   ```bash
   netsh int tcp show global
   ```

---

## Backup and Restore Issues

### Backup Creation Fails

**Symptom:** `BackupCreateError` or missing components

**Solutions:**
1. Check disk space in backup directory
2. Verify write permissions to backup folder
3. Run as Administrator for full registry access

### Backup Not Found

**Symptom:** `BackupNotFoundError: Backup not found: xyz`

**Solutions:**
1. List available backups:
   ```bash
   python -m abso restore list
   ```
2. Use `latest` to restore most recent:
   ```bash
   python -m abso restore latest
   ```
3. Check backup directory exists

### Corrupted Backup

**Symptom:** `BackupCorruptedError: Manifest is corrupted`

**Causes:**
- Incomplete backup due to crash/power loss
- Manual editing of backup files
- Disk errors

**Solutions:**
1. Try a different backup
2. Manually inspect manifest.json for syntax errors
3. If only one component is corrupted, manually restore others

### Restore Doesn't Fix Issue

**Symptom:** Settings restored but problems persist

**Solutions:**
1. Some settings require a **reboot** to take effect
2. Check if application cached old settings
3. Verify restore succeeded:
   ```bash
   python -m abso audit
   ```

---

## Performance Issues

### Audit Takes Too Long

**Symptom:** Audit operation is slow (>10 seconds)

**Causes:**
- WMI queries can be slow
- Large number of network interfaces
- Antivirus scanning

**Solutions:**
1. Audit specific category:
   ```bash
   python -m abso audit --category network
   ```
2. Disable real-time antivirus scanning temporarily

### High CPU During Detection

**Symptom:** CPU spikes during hardware detection

**Cause:** WMI queries are CPU-intensive

**Solution:** This is normal and temporary. Detection caches results.

---

## Recovery Procedures

### Reverting All Changes

If A.B.S.O. caused issues:

1. **From Backup:**
   ```bash
   python -m abso restore latest
   ```

2. **Manual Reset (if backups unavailable):**

   **Power Plan:**
   ```bash
   powercfg /setactive SCHEME_BALANCED
   ```

   **Network Settings:**
   ```bash
   netsh int tcp set global autotuninglevel=normal
   netsh int tcp set global ecncapability=default
   ```

   **Timer Resolution:**
   Restart your PC to reset timer resolution.

   **Registry Settings:**
   Use System Restore point if available.

### Creating a System Restore Point

Before using A.B.S.O., create a Windows restore point:

1. Search "Create a restore point" in Windows
2. Click "Create" button
3. Name it "Before A.B.S.O."

### Emergency Recovery

If Windows is unstable after applying settings:

1. **Safe Mode:**
   - Restart and press F8 / Shift+F8
   - Select Safe Mode
   - Run restore from backup

2. **System Restore:**
   - Boot to Windows Recovery
   - Choose System Restore
   - Select restore point before A.B.S.O.

---

## Common Error Messages

| Error | Cause | Solution |
|-------|-------|----------|
| `WMI module not available` | pywin32 not installed | `pip install pywin32` |
| `nvidia-smi not found` | Nvidia tools not in PATH | Add NVSMI to PATH |
| `Permission denied` | Not running as admin | Run as Administrator |
| `Registry key not found` | Setting doesn't exist on this Windows version | Safe to ignore |
| `Timeout setting TCP global` | netsh command hung | Restart and retry |
| `Backup manifest not found` | Incomplete backup | Use different backup |

---

## Logging and Debugging

### Enable Verbose Logging

```bash
python -m abso audit --verbose
```

### View Debug Logs

A.B.S.O. uses Python's logging module:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Capture Full Error

```python
import traceback
try:
    # A.B.S.O. operation
except Exception as e:
    traceback.print_exc()
```

---

## Getting Help

### Before Reporting an Issue

1. Check this troubleshooting guide
2. Try running as Administrator
3. Create a backup before testing
4. Note your Windows version and build

### Reporting a Bug

Include:
1. Windows version (`winver`)
2. Python version (`python --version`)
3. Full error message and stack trace
4. Steps to reproduce
5. Hardware info (GPU, CPU)

### Community Resources

- Check project issues on GitHub
- Review closed issues for similar problems
- Read the API documentation for correct usage

---

## Quick Reference

### Common Commands

```bash
# Check if running as admin
python -c "import ctypes; print('Admin' if ctypes.windll.shell32.IsUserAnAdmin() else 'Not Admin')"

# List all backups
python -c "from abso.core.backup import BackupManager; from pathlib import Path; print(BackupManager(Path('backups')).list_backups())"

# Quick audit
python -m abso audit

# Restore last backup
python -m abso restore latest
```

### File Locations

| Item | Path |
|------|------|
| Backups | `./backups/` |
| Config (if enabled) | `./config.yaml` |
| Logs | Console output (no file logging by default) |
