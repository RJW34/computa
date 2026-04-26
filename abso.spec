# -*- mode: python ; coding: utf-8 -*-

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
    ],
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
    strip=True,  # Strip debug symbols
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
