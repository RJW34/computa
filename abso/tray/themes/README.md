# Tray Theme Packs

The A.B.S.O. tray's icons and sound cues are themeable. A theme is a folder
under `abso/tray/themes/<name>/` containing a `theme.json` manifest plus any
`.ico` / `.mp3` / `.wav` assets it references.

Select a theme with the `theme` key in `%APPDATA%\ABSO\tray-config.json`:

```json
{ "theme": "default" }
```

Changing the theme takes effect the next time the tray starts (use the tray's
**Restart Tray** menu item).

## Manifest format

Every key is optional. Anything missing falls back to the built-in defaults:
programmatically generated icons and Windows system sound cues, so a theme can
override as little or as much as it wants.

```json
{
  "name": "My Theme",
  "description": "What this theme looks and sounds like.",
  "icons": {
    "idle": "idle.ico",
    "active": "active.ico",
    "gaming": "gaming.ico",
    "applying": "applying.ico",
    "warning": null,
    "error": null,
    "applySequence": ["frame0.ico", "frame1.ico", "frame2.ico", "final.ico"]
  },
  "sounds": {
    "success": "success.mp3",
    "fail": "system:Hand",
    "vrrWarning": "system:Exclamation",
    "restart": "none"
  }
}
```

### Icon keys

| Key | Shown when |
|-----|------------|
| `idle` | Tray is ready with no profile active (also during tray startup/restart) |
| `active` | A profile is applied |
| `gaming` | A monitored game is running |
| `applying` | A profile apply is in flight |
| `warning` | A non-fatal problem needs attention |
| `error` | An apply failed |
| `applySequence` | Frames of the short celebration animation after a successful apply |

Icon values are filenames relative to the theme folder, or `null` to use the
generated icon for that state.

### Sound keys

| Key | Played when |
|-----|-------------|
| `success` | Profile apply succeeded |
| `fail` | Profile apply failed or profile missing |
| `vrrWarning` | A no-sync profile needs a manual monitor OSD change |
| `restart` | The tray finished restarting successfully |

Sound values are one of:

- a filename relative to the theme folder (`.mp3` or `.wav`),
- `"system:<Name>"` for a Windows system sound — `Asterisk`, `Beep`,
  `Exclamation`, `Hand`, or `Question` (respects the user's sound scheme),
- `"none"` to silence that cue.

## Local (personal) themes

Only `themes/default/` is committed to the repository. Every other folder under
`themes/` is gitignored, so personal themes — including ones containing media
you don't have redistribution rights for — stay on your machine and never ship
with the repo. `build.py deploy` copies all locally present themes into the
installed tray runtime.
