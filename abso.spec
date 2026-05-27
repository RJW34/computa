# ruff: noqa: F821, UP009
# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path

# Exclude unused modules to reduce binary size
EXCLUDES = [
    'tkinter', '_tkinter', 'tcl', 'tk',
    'matplotlib', 'numpy', 'pandas', 'scipy',
    'PIL', 'cv2', 'opencv',
    'pytest', 'unittest', 'doctest',
    'IPython', 'jupyter', 'notebook',
    'sphinx', 'docutils',
    'http.server', 'xmlrpc',
    'lib2to3', 'distutils', 'setuptools', 'pip',
]

ROOT_DIR = Path(globals().get('__file__', 'abso.spec')).resolve().parent
TRAY_DIR = ROOT_DIR / 'abso' / 'tray'
TRAY_BUNDLE_EXTENSIONS = {'.ico', '.json', '.mp3', '.ps1', '.vbs'}
TRAY_BUNDLE_EXCLUDE_FILENAMES = {
    # Deprecated ad-hoc diagnostics used broad process killing and should not
    # ship into the one-file fallback bundle.
    '_diag-and-restart.ps1',
    '_restart-tray.ps1',
    # User tray settings live under %APPDATA%\ABSO, not beside the scripts.
    'tray-config.json',
}


def _repo_relative(path):
    return str(path.relative_to(ROOT_DIR))


def _tray_data_files():
    if not TRAY_DIR.exists():
        return []
    return [
        (_repo_relative(path), 'abso\\tray')
        for path in sorted(TRAY_DIR.iterdir(), key=lambda item: item.name.lower())
        if (
            path.is_file()
            and path.suffix.lower() in TRAY_BUNDLE_EXTENSIONS
            and path.name not in TRAY_BUNDLE_EXCLUDE_FILENAMES
        )
    ]


TRAY_DATA_FILES = _tray_data_files()

a = Analysis(
    ['abso\\__main__.py'],
    pathex=[],
    binaries=[],
    # Bundled data files. These resolve via Path(__file__).parent at runtime;
    # PyInstaller rewrites __file__ to the unpacked _MEIxxxxxx temp dir, so
    # the YAML/JSON files must be co-located with their module.
    datas=[
        ('abso\\data\\debloat_tweaks.yaml', 'abso\\data'),
        ('abso\\data\\monitor_osd.yaml', 'abso\\data'),
        ('abso\\core\\manifests\\game_detection.json', 'abso\\core\\manifests'),
        ('abso\\core\\manifests\\integration_test_matrix.json', 'abso\\core\\manifests'),
        ('abso\\core\\manifests\\linter_rules.json', 'abso\\core\\manifests'),
    ] + TRAY_DATA_FILES,
    hiddenimports=['win32gui', 'win32process', 'win32security', 'pynvml', 'abso.core.vrr'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=2,  # Optimize bytecode
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='abso',
    debug=False,
    bootloader_ignore_signals=False,
    # PyInstaller's ``strip`` option invokes an external GNU/Unix ``strip``
    # binary. That is not present on normal Windows machines and produces a
    # warning for every collected binary, burying real build issues.
    strip=sys.platform != 'win32',
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['gui\\src-tauri\\icons\\icon.ico'],
)
