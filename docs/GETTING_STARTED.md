# Getting started with computa

A first-time walkthrough for testers. Plan on about 10 minutes, plus one
reboot if your first profile asks for it.

**Requirements:** Windows 11 (64-bit) and an account that can approve an
admin (UAC) prompt. Any GPU works. NVIDIA gets the deepest tuning; AMD
support is **experimental and untested on real hardware**, so reports from
Radeon owners are especially useful.

---

## 1. Install

1. Download **`computa-setup.exe`** from the
   [latest release](https://github.com/RJW34/computa/releases/latest).
2. Double-click it. The installer isn't code-signed, so Windows SmartScreen
   may say *"Windows protected your PC"*. Click **More info → Run anyway**.
3. Follow the wizard. The install is per-user, so there's no admin prompt
   yet. Leave **"Run first-time setup now (recommended)"** checked on the
   last page.

Installing doesn't change any Windows or game settings.

## 2. First-time setup window

Setup opens a small window and shows **one UAC prompt**. Approve it so
setup can read hardware and take a snapshot.

| Page | What happens | What to do |
|---|---|---|
| **Options** | Shows what it found on your PC (GPU, monitor, Windows build) and what setup may do. | Keep **Safety snapshot** on. **Start tray with Windows** is optional. Only enable *known-bad update removal* if you know you want it. |
| **Survey** | Lists the games it detected (pre-checked) and asks about HDR, VRR/G-SYNC and streaming. | Check the games you play. Your answers only decide which profiles the tray menu shows. Leave everything unchecked to see the full list. |
| **Progress** | Takes the baseline snapshot and prepares the tray. | Wait for it to finish. |
| **Done** | Summary, plus a restart note if one is needed. | Click **Open the tray now**. |

**Setup doesn't apply any optimizations.** It only records a baseline, so
everything can be put back later.

You can re-run setup later from **Start menu → computa → computa setup**.

## 3. Apply your first profile

1. Find the computa icon near the clock. If it isn't there, check the `^`
   overflow area.
2. Click it and pick the profile for the game you're about to play, for
   example *Overwatch 2 — G-SYNC*. A backup is taken automatically before
   anything changes.
3. If the tray says a **restart is required**, reboot before you judge the
   results. Some settings, such as GPU scheduling, only take effect after a
   restart.
4. Some games need in-game settings that computa can't write, such as
   turning on NVIDIA Reflex. The tray shows a reminder when this applies.

**Picking a lane:**

- **No Sync**: lowest latency, with possible screen tearing.
- **G-SYNC / VRR**: smooth and tear-free. Use it if your monitor supports it.
- **HDR**: only if you play with Windows HDR turned on.
- **Streaming**: use this while OBS, Discord streaming or a capture tool is
  running. It keeps those apps alive.
- **Desktop**: returns to normal everyday settings.

## 4. Check it worked (optional)

Open an **administrator** terminal:

```powershell
computa state --verify     # is the active profile actually in effect?
computa health             # overall install health
```

If you didn't add computa to PATH during install, run these from
`%LOCALAPPDATA%\AdaptiveBattleStationOptimizer\`.

## 5. Undo anything

| Want to… | Do this |
|---|---|
| Undo the last profile apply | `computa restore latest` (admin terminal) |
| Go back to everyday settings | Tray → pick a **Desktop** profile |
| See every backup | `computa backups` |
| Put the PC back to how it was before computa | **Settings → Apps → computa → Uninstall**. The uninstaller offers to restore the setup-time baseline. Or run `computa uninstall`. |

## 6. Reporting problems

Please send:

1. What you did, what you expected, and what happened instead.
2. A diagnostics bundle. In an **admin** terminal, run:
   ```powershell
   computa health --bundle
   ```
   It prints the path of a ZIP that contains the health report, verify
   details, recent backups and the tray logs. Attach that ZIP.
3. The output of `computa detect`, which shows your hardware.

Open an issue on the repo, or send these to the person who invited you.

## Known limitations

- No auto-update. New versions mean downloading and running the new
  `computa-setup.exe` again. Run `computa update-check` to see whether a newer
  release exists.
- AMD GPUs, non-English Windows, and display scaling above 100% are
  untested. The setup window may look cramped at 125% or 150%.
- The game list is limited to the built-in profiles (`computa profiles`).
  Games without a profile aren't tuned.
- The tray's internal file names still use the old project name, **ABSO**.
  That's expected.
