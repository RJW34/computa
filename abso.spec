# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec file for A.B.S.O. (Adaptive Battle Station Optimizer).

This creates a standalone Windows executable that bundles:
- The ABSO CLI tool
- All Python dependencies
- NPI tool location hints

Build command:
    pyinstaller abso.spec

Output:
    dist/abso.exe - Single-file Windows executable
"""

import sys
from pathlib import Path

# Add project root to path
block_cipher = None

a = Analysis(
    ['abso\\main.py'],
    pathex=[],
    binaries=[],
    datas=[
        # Include profile data if any YAML/JSON configs exist
        # ('profiles/*.yaml', 'profiles'),
    ],
    hiddenimports=[
        # WMI and Windows-specific modules
        'wmi',
        'win32api',
        'win32con',
        'win32gui',
        'win32process',
        'pywintypes',
        # Rich console
        'rich',
        'rich.console',
        'rich.table',
        'rich.panel',
        'rich.progress',
        'rich.prompt',
        # Click CLI
        'click',
        # All settings handlers
        'abso.settings.windows',
        'abso.settings.nvidia',
        'abso.settings.registry',
        'abso.settings.power',
        'abso.settings.network',
        'abso.settings.mouse',
        'abso.settings.graphics',
        'abso.settings.memory',
        'abso.settings.timer',
        'abso.settings.tasks',
        'abso.settings.services',
        'abso.settings.audio',
        'abso.settings.storage',
        'abso.settings.visual',
        'abso.settings.updates',
        'abso.settings.process_priority',
        # Profile modules
        'abso.profiles.slippi_melee',
        'abso.profiles.cod_bo7',
        'abso.profiles.diablo4',
        'abso.profiles.rivals2',
        # Core modules
        'abso.core.detector',
        'abso.core.auditor',
        'abso.core.applier',
        'abso.core.backup',
        'abso.core.game_detector',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'PIL',
        'cv2',
        'tensorflow',
        'torch',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='abso',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # CLI tool needs console
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # Add icon path here if available: 'assets/abso.ico'
    version=None,  # Add version info here if needed
    uac_admin=True,  # Request admin privileges - required for registry access
)
