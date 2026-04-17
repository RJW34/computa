# ABSO GUI - Product Requirements Document

> **A.B.S.O.** (Adaptive Battle Station Optimizer) GUI Frontend

This document defines the requirements, design decisions, and implementation guidance for building a graphical user interface for ABSO.

---

## Table of Contents

1. [Overview](#overview)
2. [Design Decisions](#design-decisions)
3. [Technology Stack](#technology-stack)
4. [Application Structure](#application-structure)
5. [Screen Specifications](#screen-specifications)
6. [Component Library](#component-library)
7. [Data Flow](#data-flow)
8. [Error Handling](#error-handling)
9. [Accessibility](#accessibility)
10. [Implementation Phases](#implementation-phases)

---

## Overview

### Purpose

Provide a visual interface for ABSO that allows users to:
- View system hardware and optimization status at a glance
- Apply game-specific optimization profiles through a guided wizard
- Manage settings with simple defaults and optional advanced control
- Create and restore configuration backups
- Understand what each setting does without CLI knowledge

### Target User

Single enthusiast gamer on Windows 11 who wants aggressive latency optimization with safety (backup/rollback).

### Design Philosophy

- **Clean Minimal**: Light/dark toggle, clean lines, minimal decoration (Windows Settings aesthetic)
- **Progressive Disclosure**: Simple by default, advanced when needed
- **Guided Experience**: Wizard flows for complex operations
- **Non-Destructive**: Always prompt for backups before changes

---

## Design Decisions

These decisions were made based on user requirements:

| Aspect | Decision | Rationale |
|--------|----------|-----------|
| **Profile Selection** | Wizard Flow | Step-by-step guidance prevents mistakes |
| **Dashboard Layout** | Card Dashboard | Quick access to all features from home |
| **Settings Complexity** | Simple + Advanced | Accessible to beginners, powerful for experts |
| **Visual Style** | Clean Minimal | Professional, matches Windows 11 aesthetic |
| **Audit Display** | Inline Badges | Issues visible at a glance, details on click |
| **Backup Management** | Modal Prompt | User always aware before changes |
| **System Tray** | No | Standard window application |
| **Hardware Display** | Compact Summary | Essential info visible, no clutter |

---

## Technology Stack

### Recommended Stack

```
Frontend:    React 18 + TypeScript
Bundler:     Vite
Desktop:     Tauri 2.0 (Rust backend, web frontend)
Styling:     Tailwind CSS + shadcn/ui components
State:       Zustand (lightweight, simple)
Icons:       Lucide React
```

### Why Tauri over Electron?

- Smaller bundle size (~10MB vs ~150MB)
- Better performance (native Rust backend)
- Lower memory footprint
- Can invoke Python CLI directly via Tauri commands
- Windows-native feel

### Backend Integration

The GUI wraps the existing Python CLI. Communication options:

1. **Primary**: Invoke `python -m abso <command>` via Tauri shell commands
2. **Alternative**: Python subprocess with JSON output mode (add `--json` flag to CLI)
3. **Future**: Direct Python FFI via PyO3 (if performance becomes an issue)

Add JSON output support to CLI commands:
```python
@click.option('--json', is_flag=True, help='Output as JSON for GUI integration')
```

---

## Application Structure

### Window Configuration

```
Title:           ABSO - Adaptive Battle Station Optimizer
Default Size:    1200 x 800 px
Minimum Size:    900 x 600 px
Resizable:       Yes
Titlebar:        Native Windows (not custom)
Theme:           System preference (light/dark toggle available)
```

### Navigation Model

**Card Dashboard Home** → Click card → Feature Page → Back to Home

No persistent navigation bar. Each page has a back button to return home.

### File Structure

```
src/
├── components/
│   ├── ui/                    # shadcn/ui base components
│   ├── cards/                 # Dashboard action cards
│   ├── wizard/                # Profile wizard steps
│   └── settings/              # Settings panels
├── pages/
│   ├── Home.tsx               # Dashboard with action cards
│   ├── ProfileWizard.tsx      # Multi-step profile apply wizard
│   ├── SettingsEditor.tsx     # Settings with simple/advanced toggle
│   ├── AuditDetails.tsx       # Full audit results page
│   └── BackupManager.tsx      # Backup history and restore
├── hooks/
│   ├── useHardware.ts         # Hardware detection state
│   ├── useAudit.ts            # Audit results state
│   └── useBackups.ts          # Backup list state
├── lib/
│   ├── api.ts                 # Tauri command invocations
│   └── types.ts               # TypeScript interfaces
└── stores/
    └── appStore.ts            # Zustand global state
```

---

## Screen Specifications

### 1. Home Dashboard

The main screen users see on launch.

#### Layout

```
┌─────────────────────────────────────────────────────────────┐
│  ABSO                                          [🌙] [⚙️]    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─ Hardware Summary ─────────────────────────────────────┐ │
│  │ RTX 4080 · i9-14900K · 32GB · 240Hz G-Sync            │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  🎮          │  │  🔍          │  │  ⚙️          │      │
│  │  Apply       │  │  Audit       │  │  Settings    │      │
│  │  Profile     │  │  System      │  │  Editor      │      │
│  │              │  │         ⚠️ 3 │  │              │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  💾          │  │  📊          │  │  ⏱️          │      │
│  │  Backups     │  │  Reports     │  │  Timer       │      │
│  │              │  │              │  │  Resolution  │      │
│  │              │  │              │  │              │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│                                                             │
│  ┌─ Status Bar ───────────────────────────────────────────┐ │
│  │ ✓ Admin · Last backup: 2 hours ago · NPI: Available   │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

#### Components

**Hardware Summary Bar**
- Single line showing: GPU · CPU · RAM · Primary Monitor Refresh + VRR type
- Clicking expands to show per-component details (modal or drawer)

**Action Cards** (6 cards in 3x2 grid)

| Card | Icon | Title | Subtitle | Badge |
|------|------|-------|----------|-------|
| Apply Profile | 🎮 | Apply Profile | Optimize for a specific game | - |
| Audit System | 🔍 | Audit System | Check for optimization issues | Issue count (⚠️ N) |
| Settings Editor | ⚙️ | Settings | Fine-tune individual settings | - |
| Backups | 💾 | Backups | Manage restore points | Backup count |
| Reports | 📊 | Reports | View in-game setting guides | - |
| Timer Resolution | ⏱️ | Timer | Set system timer resolution | Current value |

**Status Bar**
- Admin status (required for most operations)
- Last backup timestamp
- NPI (Nvidia Profile Inspector) availability
- If not admin: Show "Restart as Admin" button

#### Interactions

- Click card → Navigate to feature page
- Click hardware summary → Expand hardware details modal
- Click audit badge → Navigate to audit details
- Dark mode toggle in header
- Settings gear in header → App preferences

---

### 2. Profile Wizard

Multi-step wizard for applying game optimization profiles.

#### Step 1: Select Game

```
┌─────────────────────────────────────────────────────────────┐
│  ← Back                    Apply Profile                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Step 1 of 4: Select Game                                   │
│  ━━━━━━━━━━○○○○                                            │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 🎮 Slippi Melee                          [Detected] │   │
│  │    Ultra-low latency for competitive SSBM           │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 🎮 Rivals of Aether 2                               │   │
│  │    VRR-optimized for UE5 fighting game              │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 🎮 Fortnite                                         │   │
│  │    Low latency with Nvidia Reflex                   │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 🎮 Diablo 4                                         │   │
│  │    Balanced performance for ARPG                    │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│                                            [Next →]         │
└─────────────────────────────────────────────────────────────┘
```

- Show "[Detected]" badge for games found on system
- Selected game has highlighted border
- Next button disabled until selection made

#### Step 2: Review Settings

```
┌─────────────────────────────────────────────────────────────┐
│  ← Back                    Apply Profile                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Step 2 of 4: Review Settings                               │
│  ━━━━━━━━━━━━━━━━○○○○                                      │
│                                                             │
│  Slippi Melee - Minimum Latency                            │
│                                                             │
│  This profile will change:                                  │
│                                                             │
│  ┌─ Windows ──────────────────────────────────────────┐    │
│  │ • Game Mode: ON                                     │    │
│  │ • HAGS: OFF (Dolphin doesn't benefit)              │    │
│  │ • Fullscreen Optimizations: DISABLED               │    │
│  └────────────────────────────────────────────────────┘    │
│                                                             │
│  ┌─ Nvidia ───────────────────────────────────────────┐    │
│  │ • Low Latency Mode: ON                              │    │
│  │ • G-Sync: OFF (fixed 60fps)                        │    │
│  │ • VSync: OFF                                        │    │
│  └────────────────────────────────────────────────────┘    │
│                                                             │
│  ┌─ Power ────────────────────────────────────────────┐    │
│  │ • Power Plan: Ultimate Performance                  │    │
│  └────────────────────────────────────────────────────┘    │
│                                                             │
│  [Show all settings...]                                     │
│                                                             │
│                                 [← Previous]  [Next →]      │
└─────────────────────────────────────────────────────────────┘
```

- Collapsible sections per handler category
- "Show all settings" expands full details
- Each setting shows current → new value if different

#### Step 3: Backup Options

```
┌─────────────────────────────────────────────────────────────┐
│  ← Back                    Apply Profile                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Step 3 of 4: Backup Options                                │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━○○○                           │
│                                                             │
│  Before applying changes, ABSO will create a backup         │
│  so you can restore your previous settings if needed.       │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ ◉ Create backup before applying (Recommended)       │   │
│  │   A restore point will be saved automatically       │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ ○ Skip backup                                        │   │
│  │   ⚠️ You won't be able to undo these changes        │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─ Existing Backups ─────────────────────────────────┐    │
│  │ • 2024-12-29 14:30 - Before Rivals 2 profile        │    │
│  │ • 2024-12-28 09:15 - Before Slippi profile          │    │
│  └────────────────────────────────────────────────────┘    │
│                                                             │
│                                 [← Previous]  [Apply →]     │
└─────────────────────────────────────────────────────────────┘
```

- Default: Create backup (radio selected)
- Show warning if skipping backup
- List recent backups for context

#### Step 4: Applying (Progress)

```
┌─────────────────────────────────────────────────────────────┐
│                         Apply Profile                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Step 4 of 4: Applying Changes                              │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━                   │
│                                                             │
│                                                             │
│                    Applying Slippi Melee                    │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ ████████████████████░░░░░░░░░░░░░░░░░░░░░░░  45%    │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ✓ Backup created                                          │
│  ✓ Windows settings applied                                │
│  ⟳ Applying Nvidia settings...                             │
│  ○ Power settings                                          │
│  ○ Registry settings                                       │
│  ○ Mouse settings                                          │
│                                                             │
│                                                             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

- Real-time progress bar
- Checkmarks for completed steps
- Spinner for current step
- Empty circles for pending

#### Step 4: Complete

```
┌─────────────────────────────────────────────────────────────┐
│                         Apply Profile                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│                        ✓ Success!                           │
│                                                             │
│  Slippi Melee profile has been applied.                     │
│                                                             │
│  ┌─ In-Game Settings ─────────────────────────────────┐    │
│  │                                                     │    │
│  │  For best results, also configure these in-game:   │    │
│  │                                                     │    │
│  │  • Graphics Backend: Vulkan                         │    │
│  │  • VSync: OFF                                       │    │
│  │  • Fullscreen: Exclusive                            │    │
│  │  • Internal Resolution: Native                      │    │
│  │                                                     │    │
│  │  [Copy to Clipboard]    [View Full Report]         │    │
│  └────────────────────────────────────────────────────┘    │
│                                                             │
│  ⚠️ Some changes may require a restart to take effect.     │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐                        │
│  │  Undo        │  │  Done        │                        │
│  │  (Restore)   │  │  (Go Home)   │                        │
│  └──────────────┘  └──────────────┘                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

- Success state with checkmark
- In-game settings recommendations (from profile)
- Copy to clipboard for in-game settings
- Link to full report
- Undo button (immediate restore from just-created backup)
- Done button returns to home

---

### 3. Settings Editor

Fine-grained control over individual settings.

#### Layout

```
┌─────────────────────────────────────────────────────────────┐
│  ← Back                    Settings                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  [Simple]  [Advanced]                    [Reset All]        │
│                                                             │
│  ┌─ Windows ──────────────────────────────────────────┐    │
│  │                                                     │    │
│  │  Game Mode                              [  ON  ]   │    │
│  │  Prioritizes gaming, reduces background activity   │    │
│  │                                                     │    │
│  │  Game Bar                               [  OFF ]   │    │
│  │  Xbox Game Bar overlay (adds overhead)             │    │
│  │                                                     │    │
│  │  HAGS                                   [  ON  ]   │    │
│  │  Hardware-Accelerated GPU Scheduling               │    │
│  │  ℹ️ Game-dependent. DX12/UE5 benefits, others may not│   │
│  │                                                     │    │
│  └────────────────────────────────────────────────────┘    │
│                                                             │
│  ┌─ Nvidia ───────────────────────────────────────────┐    │
│  │                                                     │    │
│  │  Low Latency Mode                    [▼ On      ]  │    │
│  │  Reduces render queue (DX9/11 only)                │    │
│  │                                                     │    │
│  │  Power Management                    [▼ Max Perf]  │    │
│  │  GPU power state preference                        │    │
│  │                                                     │    │
│  └────────────────────────────────────────────────────┘    │
│                                                             │
│  ┌─ Power ────────────────────────────────────────────┐    │
│  │  Active Power Plan                   [▼ Ultimate ]  │   │
│  └────────────────────────────────────────────────────┘    │
│                                                             │
│                                            [Apply Changes]  │
└─────────────────────────────────────────────────────────────┘
```

#### Simple vs Advanced Mode

**Simple Mode** (default):
- Shows only the most impactful settings
- Toggles and simple dropdowns
- No technical jargon
- Settings: Game Mode, Game Bar, HAGS, Power Plan, Low Latency Mode

**Advanced Mode**:
- All settings visible
- Registry values editable
- Per-handler sections expandable
- Technical explanations
- Includes: System Responsiveness slider, Win32 Priority, Nagle toggle, MPO, FSO, Mouse curves, Timer resolution, Service toggles, Memory settings

#### Setting Control Types

| Setting Type | Control |
|-------------|---------|
| Boolean (on/off) | Toggle switch |
| Enum (few options) | Dropdown select |
| Numeric range | Slider with value label |
| Text/path | Input field |

---

### 4. Audit Details

Full audit results with filtering.

#### Layout

```
┌─────────────────────────────────────────────────────────────┐
│  ← Back                    System Audit                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  [🔴 Critical: 1]  [🟡 Warning: 5]  [🔵 Info: 3]           │
│                                                             │
│  Filter: [All ▼]  [All Categories ▼]          [Re-scan]    │
│                                                             │
│  ┌─ 🔴 CRITICAL ──────────────────────────────────────┐    │
│  │                                                     │    │
│  │  VBS / Memory Integrity Enabled                     │    │
│  │  Current: ON  →  Optimal: OFF                       │    │
│  │  Category: Windows                                  │    │
│  │                                                     │    │
│  │  [▼ Why does this matter?]                         │    │
│  │  Virtualization-Based Security adds ~5% CPU        │    │
│  │  overhead. For gaming, the security benefit        │    │
│  │  rarely outweighs the performance cost.            │    │
│  │                                                     │    │
│  │  ⚠️ Requires reboot to change                      │    │
│  │                                           [Fix]     │    │
│  └────────────────────────────────────────────────────┘    │
│                                                             │
│  ┌─ 🟡 WARNING ───────────────────────────────────────┐    │
│  │                                                     │    │
│  │  Game Bar Enabled                                   │    │
│  │  Current: ON  →  Optimal: OFF                       │    │
│  │  Category: Windows                         [Fix]    │    │
│  │                                                     │    │
│  │  Mouse Acceleration Enabled                         │    │
│  │  Current: ON  →  Optimal: OFF                       │    │
│  │  Category: Mouse                           [Fix]    │    │
│  │                                                     │    │
│  └────────────────────────────────────────────────────┘    │
│                                                             │
│                                            [Fix All (6)]    │
└─────────────────────────────────────────────────────────────┘
```

#### Features

- Severity filter chips (toggle visibility)
- Category dropdown filter (Windows, Nvidia, Power, etc.)
- Each issue shows current vs optimal value
- Expandable "Why does this matter?" explanation
- Individual "Fix" buttons per issue
- "Fix All" button for bulk apply
- "Re-scan" button to refresh audit

---

### 5. Backup Manager

View and restore backups.

#### Layout

```
┌─────────────────────────────────────────────────────────────┐
│  ← Back                    Backups                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─ 2024-12-29 14:30:22 ──────────────────────────────┐    │
│  │  Before: Rivals of Aether 2 profile                 │    │
│  │  Components: Windows, Nvidia, Power, Registry       │    │
│  │                                                     │    │
│  │  [View Details]              [Restore]  [Delete]    │    │
│  └────────────────────────────────────────────────────┘    │
│                                                             │
│  ┌─ 2024-12-28 09:15:44 ──────────────────────────────┐    │
│  │  Before: Slippi Melee profile                       │    │
│  │  Components: Windows, Nvidia, Power, Registry,      │    │
│  │              Mouse, Network                         │    │
│  │                                                     │    │
│  │  [View Details]              [Restore]  [Delete]    │    │
│  └────────────────────────────────────────────────────┘    │
│                                                             │
│  ┌─ 2024-12-27 18:42:11 ──────────────────────────────┐    │
│  │  Manual backup                                      │    │
│  │  Components: All                                    │    │
│  │                                                     │    │
│  │  [View Details]              [Restore]  [Delete]    │    │
│  └────────────────────────────────────────────────────┘    │
│                                                             │
│                                       [Create Backup Now]   │
└─────────────────────────────────────────────────────────────┘
```

#### Interactions

- **View Details**: Modal showing all backed-up values
- **Restore**: Confirmation modal → apply backup → show result
- **Delete**: Confirmation modal → delete backup folder
- **Create Backup Now**: Creates manual backup with current settings

---

### 6. Timer Resolution

Quick access to timer resolution control.

#### Layout

```
┌─────────────────────────────────────────────────────────────┐
│  ← Back                Timer Resolution                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Current Resolution: 15.625 ms (default)                    │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                                                     │   │
│  │  0.5ms ──────────────●─────────────────── 15.625ms  │   │
│  │         Gaming                           Default    │   │
│  │                                                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  Selected: 0.5 ms                                          │
│                                                             │
│  ℹ️ What is timer resolution?                              │
│                                                             │
│  Timer resolution affects system scheduling granularity.    │
│  Lower values (0.5ms) improve frame pacing consistency     │
│  and thread wake precision.                                │
│                                                             │
│  ⚠️ Note: This does NOT directly reduce input latency.     │
│  For input latency, use Nvidia Reflex or frame queue       │
│  management.                                               │
│                                                             │
│  ☐ Keep resolution while ABSO is running                   │
│                                                             │
│                                            [Apply]          │
└─────────────────────────────────────────────────────────────┘
```

---

### 7. Reports

View in-game settings recommendations.

#### Layout

```
┌─────────────────────────────────────────────────────────────┐
│  ← Back                    Reports                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Select a game to view recommended in-game settings:        │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ Slippi Melee │  │ Rivals 2     │  │ Fortnite     │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│                                                             │
│  ═══════════════════════════════════════════════════════   │
│                                                             │
│  Slippi Melee - In-Game Settings                           │
│                                                             │
│  ## Graphics                                                │
│  - **Backend**: Vulkan (lower latency than OpenGL)         │
│  - **VSync**: OFF                                          │
│  - **Fullscreen**: Exclusive                               │
│  - **Internal Resolution**: Native                         │
│                                                             │
│  ## Audio                                                   │
│  - **Backend**: Cubeb (lowest latency)                     │
│  - **Latency**: Lowest stable setting                      │
│                                                             │
│  ## Controller                                              │
│  - **Adapter Mode**: Wii U / GameCube Adapter              │
│  - **Background Input**: ON                                │
│                                                             │
│                    [Copy to Clipboard]  [Export as PDF]     │
└─────────────────────────────────────────────────────────────┘
```

- Markdown rendering for report content
- Copy button for easy pasting
- Optional PDF export

---

## Component Library

Use **shadcn/ui** components as the base, customized for ABSO's needs.

### Core Components

| Component | Usage |
|-----------|-------|
| `Button` | Primary, secondary, destructive variants |
| `Card` | Dashboard action cards, settings groups |
| `Toggle` | Boolean settings |
| `Select` | Dropdown choices |
| `Slider` | Numeric ranges |
| `Progress` | Apply/restore progress |
| `Badge` | Issue counts, status indicators |
| `Dialog` | Confirmations, details modals |
| `Tabs` | Simple/Advanced mode toggle |
| `Accordion` | Collapsible settings sections |
| `Alert` | Warnings, reboot required notices |

### Custom Components

| Component | Description |
|-----------|-------------|
| `ActionCard` | Dashboard card with icon, title, subtitle, optional badge |
| `SettingRow` | Label + control + description row |
| `IssueCard` | Audit issue with severity, values, fix button |
| `WizardStep` | Step indicator with progress |
| `HardwareSummary` | Compact hardware info bar |
| `StatusBar` | Bottom status with admin/backup/NPI status |

---

## Data Flow

### State Management (Zustand)

```typescript
interface AppState {
  // Hardware
  hardware: HardwareInfo | null;
  hardwareLoading: boolean;

  // Audit
  auditResults: Issue[];
  auditLoading: boolean;

  // Backups
  backups: Backup[];
  backupsLoading: boolean;

  // Settings
  currentSettings: Settings;
  pendingChanges: Partial<Settings>;

  // UI
  theme: 'light' | 'dark' | 'system';
  settingsMode: 'simple' | 'advanced';

  // Actions
  detectHardware: () => Promise<void>;
  runAudit: () => Promise<void>;
  applyProfile: (profileId: string, createBackup: boolean) => Promise<void>;
  restoreBackup: (backupId: string) => Promise<void>;
  applySettings: (settings: Partial<Settings>) => Promise<void>;
}
```

### CLI Integration

```typescript
// src/lib/api.ts
import { invoke } from '@tauri-apps/api/core';

export async function detectHardware(): Promise<HardwareInfo> {
  const result = await invoke('run_abso_command', {
    command: 'detect',
    args: ['--json']
  });
  return JSON.parse(result as string);
}

export async function runAudit(): Promise<Issue[]> {
  const result = await invoke('run_abso_command', {
    command: 'audit',
    args: ['--json', '--verbose']
  });
  return JSON.parse(result as string);
}

export async function applyProfile(
  profileId: string,
  noBackup: boolean
): Promise<ApplyResult> {
  const args = noBackup ? ['--no-backup', '--json'] : ['--json'];
  const result = await invoke('run_abso_command', {
    command: 'apply',
    args: [profileId, ...args]
  });
  return JSON.parse(result as string);
}
```

### Tauri Backend Command

```rust
// src-tauri/src/main.rs
#[tauri::command]
async fn run_abso_command(command: String, args: Vec<String>) -> Result<String, String> {
    let output = std::process::Command::new("python")
        .args(["-m", "abso", &command])
        .args(&args)
        .output()
        .map_err(|e| e.to_string())?;

    if output.status.success() {
        Ok(String::from_utf8_lossy(&output.stdout).to_string())
    } else {
        Err(String::from_utf8_lossy(&output.stderr).to_string())
    }
}
```

---

## Error Handling

### User-Facing Errors

| Error Type | Display |
|------------|---------|
| Not Admin | Banner: "Restart as Administrator to enable all features" |
| NPI Missing | Warning in Nvidia section: "Install Nvidia Profile Inspector for GPU settings" |
| Apply Failed | Modal with error details and retry option |
| Backup Failed | Toast notification with details |
| CLI Error | Modal with stderr output and "Copy Error" button |

### Graceful Degradation

- If hardware detection fails: Show "Unknown" with refresh button
- If audit fails: Show error state with retry button
- If single handler fails during apply: Continue with others, report partial success
- If NPI not installed: Hide/disable Nvidia settings, show install prompt

---

## Accessibility

- All interactive elements keyboard accessible
- Focus indicators visible
- Color not sole indicator (icons + color for severity)
- Tooltips on hover for additional context
- Screen reader labels for icons
- Minimum touch target size: 44x44px
- Contrast ratio: WCAG AA compliant

---

## Implementation Phases

### Phase 1: Foundation (MVP)

- [ ] Tauri project setup with React + TypeScript
- [ ] Basic window with dark/light theme
- [ ] Home dashboard with action cards
- [ ] Hardware detection display
- [ ] CLI integration (detect, audit commands)
- [ ] Audit results display with filtering

### Phase 2: Core Features

- [ ] Profile wizard (all 4 steps)
- [ ] Backup management page
- [ ] Apply profile with progress
- [ ] Restore from backup
- [ ] Status bar implementation

### Phase 3: Settings Editor

- [ ] Simple mode settings
- [ ] Advanced mode settings
- [ ] Per-setting apply
- [ ] Reset functionality
- [ ] Pending changes tracking

### Phase 4: Polish

- [ ] Reports page with markdown rendering
- [ ] Timer resolution page
- [ ] Hardware details modal
- [ ] Error handling improvements
- [ ] Loading states and animations
- [ ] Keyboard shortcuts

### Phase 5: Enhancements

- [ ] Add `--json` flag to all CLI commands
- [ ] Improve CLI error messages for GUI parsing
- [ ] Add progress events for long operations
- [ ] Settings persistence (window size, theme preference)

---

## CLI Modifications Required

To support the GUI, add these features to the Python CLI:

### 1. JSON Output Mode

Add `--json` flag to all commands:

```python
@click.option('--json', 'json_output', is_flag=True, help='Output as JSON')
def detect(json_output):
    result = detector.detect_all()
    if json_output:
        click.echo(json.dumps(result, default=str))
    else:
        # existing pretty output
```

### 2. Structured Errors

Return errors as JSON when `--json` flag is set:

```python
{
  "success": false,
  "error": {
    "type": "AdminRequired",
    "message": "This operation requires administrator privileges",
    "details": null
  }
}
```

### 3. Progress Events (Future)

For long operations, emit progress to stdout:

```python
{"event": "progress", "step": "backup", "status": "complete"}
{"event": "progress", "step": "windows", "status": "in_progress"}
```

---

## Notes for Implementation

1. **Start with Tauri**: Lighter than Electron, better Windows integration
2. **Use shadcn/ui**: Pre-built accessible components, easy to customize
3. **CLI First**: GUI wraps CLI, doesn't replace it
4. **Incremental JSON**: Add `--json` to commands as GUI needs them
5. **Test Early**: Test on Windows 11 with and without admin privileges
6. **Error States**: Every async operation needs loading, success, and error states

---

**This document is authoritative for GUI development.**
Defer to `CLAUDE.md` for CLI/backend architecture decisions.
