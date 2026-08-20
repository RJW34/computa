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
TRAY_BUNDLE_EXTENSIONS = {'.ico', '.json', '.mp3', '.ps1', '.vbs', '.wav'}
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


def _tray_theme_data_files():
    # Theme packs live in per-theme subfolders; whatever themes exist at build
    # time (always themes/default, plus any local personal themes) ship with
    # the bundle, preserving the themes/<name>/ layout.
    themes_dir = TRAY_DIR / 'themes'
    if not themes_dir.exists():
        return []
    return [
        (
            _repo_relative(path),
            'abso\\tray\\' + '\\'.join(path.parent.relative_to(TRAY_DIR).parts),
        )
        for path in sorted(themes_dir.rglob('*'), key=lambda item: str(item).lower())
        if path.is_file() and path.suffix.lower() in TRAY_BUNDLE_EXTENSIONS
    ]


TRAY_DATA_FILES = _tray_data_files()
TRAY_THEME_DATA_FILES = _tray_theme_data_files()

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
    ] + TRAY_DATA_FILES + TRAY_THEME_DATA_FILES,
    hiddenimports=[
        'win32gui', 'win32process', 'win32security', 'pynvml', 'abso.core.vrr',
        # Every ``import wmi`` in the codebase is lazy and exception-isolated
        # (detector, bios_detector, kb_checker, gpu_vendor, cpu_affinity,
        # interrupt_mode, amd), so a build whose environment lacks the package
        # still freezes successfully and the installed runtime silently loses
        # all WMI-backed detection (2026-08-12 deploy shipped exactly that).
        # Listed explicitly so the module is always collected; build.py
        # additionally fails the build if PyInstaller reports it missing.
        'wmi',
        # Process Lasso-class session-runtime modules. These are imported
        # lazily inside cpu_balancer (so the daemon can host them), which
        # PyInstaller's static analysis may not follow; list them explicitly so
        # the frozen exe actually contains them (otherwise the daemon's
        # exception-isolated imports would silently no-op the features).
        'abso.core.cpu_sets',
        'abso.core.efficiency_mode',
        'abso.core.cpu_limiter',
        'abso.core.watchdog',
        'abso.core.watchdog_engine',
        'abso.core.proc_actions',
        # Post-apply borderless-VRR enabler reconciliation. Imported lazily
        # inside applier.apply() (PHASE 7.5); list it so the frozen exe contains
        # it -- otherwise the exception-isolated import would silently no-op the
        # fix that keeps borderless G-SYNC from regressing to half refresh.
        'abso.core.vrr_reconcile',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=2,  # Optimize bytecode
)
pyz = PYZ(a.pure)

# PyInstaller's ``strip`` option invokes an external GNU/Unix ``strip`` binary.
# That is not present on normal Windows machines and produces a warning for
# every collected binary, burying real build issues.
STRIP = sys.platform != 'win32'
ICON = ['gui\\src-tauri\\icons\\icon.ico']

# --- Primary output: one-DIR ------------------------------------------------
# The tray invokes this backend as a short-lived subprocess (launch-sweep,
# audit, state, apply). A one-FILE build re-extracts the entire ~18 MB archive
# into %TEMP%\_MEIxxxxxx on *every* invocation, so each call paid a
# decompress + disk-write + AV-scan cost before Python even started. one-DIR
# maps the same files off disk directly and drops that per-call overhead.
#
# UPX is off for the same reason: compression trades a one-time disk saving
# for decompression work on every single launch, which is the wrong side of
# the trade for a binary the tray calls repeatedly during a gaming session.
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='computa',
    debug=False,
    bootloader_ignore_signals=False,
    strip=STRIP,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=STRIP,
    upx=False,
    upx_exclude=[],
    name='computa',
)

# --- Secondary output: one-FILE portable build ------------------------------
# Tauri sidecars must be a single self-contained file, and the release docs
# offer a portable single-exe download; one build serves both. It is not what
# the tray or the installed runtime executes, so its slower cold start never
# lands on a gaming session.
portable_exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='computa-portable',
    debug=False,
    bootloader_ignore_signals=False,
    strip=STRIP,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON,
)
