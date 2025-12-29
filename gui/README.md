# ABSO GUI

Graphical user interface for **A.B.S.O.** (Adaptive Battle Station Optimizer).

## Prerequisites

- [Node.js](https://nodejs.org/) v18+ (LTS recommended)
- [Rust](https://rustup.rs/) (for Tauri)
- Windows 11

## Setup

```bash
# Install dependencies
npm install

# Run in development mode
npm run tauri:dev

# Build for production
npm run tauri:build
```

## Development

```bash
# Run just the web frontend (without Tauri)
npm run dev

# Build the web frontend
npm run build
```

## Project Structure

```
gui/
├── src/
│   ├── components/      # React components
│   │   ├── ui/          # Base UI components (shadcn/ui)
│   │   └── cards/       # Custom card components
│   ├── pages/           # Page components
│   ├── stores/          # Zustand state stores
│   ├── lib/             # Utilities, types, API
│   └── styles/          # Global CSS
├── src-tauri/           # Tauri (Rust) backend
│   └── src/
│       └── main.rs      # Tauri commands
└── public/              # Static assets
```

## Stack

- **Frontend**: React 18 + TypeScript + Vite
- **Desktop**: Tauri 2.0
- **Styling**: Tailwind CSS + shadcn/ui
- **State**: Zustand
- **Icons**: Lucide React

## CLI Integration

The GUI wraps the ABSO Python CLI. Communication happens via Tauri commands that invoke `python -m abso <command>`.

To enable JSON output for GUI integration, add `--json` flag support to CLI commands.
