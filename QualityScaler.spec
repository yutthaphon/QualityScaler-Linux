# -*- mode: python ; coding: utf-8 -*-

# PyInstaller spec for QualityScaler on Windows and Linux.
# Build with:  pyinstaller QualityScaler.spec
# On Linux the produced binary is dist/QualityScaler (no extension, no icon flag).

import sys

from PyInstaller.utils.hooks import collect_data_files

datas = [('Assets', 'Assets'), ('AI-onnx', 'AI-onnx')]
datas += collect_data_files('customtkinter')

# PIL loads its Tk bridge lazily through a string import, so the frozen build
# has to be told about it explicitly (Pillow + PyInstaller, both platforms).
hiddenimports = ['PIL._tkinter_finder']

icon = ['Assets/logo.ico'] if sys.platform == 'win32' else []

a = Analysis(
    ['QualityScaler.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
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
    name='QualityScaler',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon,
)
