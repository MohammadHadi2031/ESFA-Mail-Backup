# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo, StringFileInfo, StringStruct, StringTable, VarFileInfo, VarStruct, VSVersionInfo,
)

# VERSION is the single source of truth for both this exe's file-version resource and the
# installer's AppVersion (installer.iss); see mailbackup/__init__.py for the runtime read.
VERSION = (Path(SPECPATH) / 'VERSION').read_text(encoding='utf-8').strip()
VERSION_PARTS = [int(part) for part in VERSION.split('.')]
VERSION_TUPLE = tuple((VERSION_PARTS + [0, 0, 0, 0])[:4])

version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=VERSION_TUPLE, prodvers=VERSION_TUPLE, mask=0x3F, flags=0x0, OS=0x4, fileType=0x1, subtype=0x0, date=(0, 0)),
    kids=[
        StringFileInfo([StringTable('040904B0', [
            StringStruct('CompanyName', 'ESFA Group'),
            StringStruct('FileDescription', 'ESFA Mail Backup'),
            StringStruct('FileVersion', VERSION),
            StringStruct('InternalName', 'EsfaMailBackup'),
            StringStruct('OriginalFilename', 'EsfaMailBackup.exe'),
            StringStruct('ProductName', 'ESFA Mail Backup'),
            StringStruct('ProductVersion', VERSION),
        ])]),
        VarFileInfo([VarStruct('Translation', [0x0409, 1200])]),
    ],
)

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[('VERSION', '.')],
    hiddenimports=[
        'webview.platforms.edgechromium',
        'webview.platforms.winforms',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='EsfaMailBackup',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    version=version_info,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='EsfaMailBackup',
)
