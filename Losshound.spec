# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build spec for a portable, single-file Losshound.exe.

Build:   pyinstaller Losshound.spec
Output:  dist/Losshound.exe   (no installer — copy it anywhere and run)

This produces a one-file, windowed (no console) executable. The app's data
(history, settings, logs) is written to %LOCALAPPDATA%\\Losshound at runtime,
never next to the exe — so the binary itself stays portable and deletable.
"""

a = Analysis(
    ['src/losshound/app.py'],
    pathex=['src'],
    binaries=[],
    datas=[
        ('config.default.json', '.'),
        ('assets/losshound-logo.png', 'assets'),
        ('assets/panel-texture.png', 'assets'),
        ('assets/header-halo.png', 'assets'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Unused QDom implementation: CVE-2026-15037 (see docs/CI_SECURITY.md).
    excludes=['tkinter', 'PySide6.QtXml'],
    noarchive=False,
    optimize=0,
)

# Fail if a hook or native dependency reintroduces the excluded component.
# Do not silently remove a DLL another component requires.
for entry in a.binaries + a.datas + a.pure:
    if any(marker in entry[0].lower() for marker in ('qtxml', 'qt6xml')):
        raise RuntimeError(f'Qt XML must not be bundled: {entry[0]}')

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Losshound',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/losshound.ico',
    version='scripts/version_info.txt',
)
