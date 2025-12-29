# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['abso\\__main__.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['win32gui', 'win32process', 'win32security', 'pynvml', 'abso.core.vrr'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
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
    strip=False,
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
