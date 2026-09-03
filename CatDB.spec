# -*- mode: python ; coding: utf-8 -*-
import os
block_cipher = None

a = Analysis(
    ['server.py'],
    pathex=[],
    binaries=[],
    datas=[('www', 'www')],
    hiddenimports=[
        'webview', 'webview.platforms.winforms',
        'pystray', 'pystray._win32',
        'aiohttp', 'aiohttp.web',
        'qrcode', 'PIL',
        'pyautogui', 'pynput', 'netifaces', 'zeroconf'
    ],
    excludes=['tkinter', 'PyQt5', 'matplotlib'],
    cipher=block_cipher,
    noarchive=False,
)
pyd = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyd, a.scripts, a.binaries, a.zipfiles, a.datas, [],
    name='CatDB',
    debug=False,
    console=False,
    upx=True,
    icon='cat_icon.ico' if os.path.exists('cat_icon.ico') else None,
)