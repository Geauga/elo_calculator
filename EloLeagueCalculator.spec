# EloLeagueCalculator.spec
# Requirement: Build the complete Windows GUI executable with bundled Tcl/Tk.
# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['elo_calculator.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=['packaging_hooks'],
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
    name='EloLeagueCalculator',
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
)

# Purpose: Configure the one-file Windows executable build.
# Upstream: elo_calculator.py and packaging_hooks.
# Upstream purpose: Provide the GUI entry point and reliable Tcl/Tk collection.
# Environment: PyInstaller 6.22+ with Python 3.12 on Windows.
# Generated: 2026-09-01 20:11 America/New_York.
# Changes: Use project hooks that bundle Tcl/Tk when runtime auto-detection fails.
