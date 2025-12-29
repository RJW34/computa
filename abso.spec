# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec file for A.B.S.O. (Adaptive Battle Station Optimizer).

This creates a standalone Windows executable that bundles:
- The ABSO CLI tool
- All Python dependencies
- Support for GUI integration via --json flag

Build command:
    pyinstaller abso.spec

Output:
    dist/abso.exe - Single-file Windows executable (~15-25MB)

For GUI distribution:
    Copy dist/abso.exe to gui/src-tauri/binaries/abso-x86_64-pc-windows-msvc.exe
"""

import sys
from pathlib import Path

block_cipher = None

a = Analysis(
    ['abso/__main__.py'],  # Use __main__.py for module-style invocation
    pathex=['.'],
    binaries=[],
    datas=[
        # Include NPI tool if bundled (optional - can also be downloaded at runtime)
        # ('tools/npi/*.exe', 'tools/npi'),
    ],
    hiddenimports=[
        # WMI and Windows-specific modules
        'wmi',
        'win32api',
        'win32con',
        'win32gui',
        'win32process',
        'win32security',
        'pywintypes',
        'pythoncom',
        # Rich console
        'rich',
        'rich.console',
        'rich.table',
        'rich.panel',
        'rich.progress',
        'rich.prompt',
        'rich.live',
        'rich.spinner',
        'rich.markdown',
        # Click CLI
        'click',
        # YAML for config
        'yaml',
        # Nvidia
        'pynvml',
        # JSON (stdlib but sometimes missed)
        'json',
        # All abso modules - core
        'abso',
        'abso.main',
        'abso.interactive',
        'abso.core',
        'abso.core.detector',
        'abso.core.auditor',
        'abso.core.applier',
        'abso.core.backup',
        'abso.core.config',
        'abso.core.game_detector',
        'abso.core.vrr',
        # All abso modules - settings handlers
        'abso.settings',
        'abso.settings.base',
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
        # All abso modules - profiles
        'abso.profiles',
        'abso.profiles.base',
        'abso.profiles.slippi_melee',
        'abso.profiles.cod_bo7',
        'abso.profiles.diablo4',
        'abso.profiles.rivals2',
        # All abso modules - utils
        'abso.utils',
        'abso.utils.admin',
        'abso.utils.wmi_helper',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude unnecessary large packages
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'PIL',
        'cv2',
        'tensorflow',
        'torch',
        'IPython',
        'notebook',
        'pytest',
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
    upx=True,  # Compress with UPX if available
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # CLI tool needs console for output
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='gui/src-tauri/icons/icon.ico' if Path('gui/src-tauri/icons/icon.ico').exists() else None,
    version='version_info.txt' if Path('version_info.txt').exists() else None,
    uac_admin=True,  # Request admin privileges - required for registry/system access
)
