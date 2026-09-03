# -*- mode: python ; coding: utf-8 -*-
import os
block_cipher = None

a = Analysis(
    ['server.py'],
    pathex=[],
    binaries=[],
    datas=[('www', 'www')],
    hiddenimports=[
        'webview', 'webview.platforms.edgechromium', 'webview.platforms.winforms', 'webview.platforms.mshtml',
        'pystray', 'pystray._win32',
        'aiohttp', 'aiohttp.web',
        'qrcode', 'PIL',
        'pyautogui', 'pynput', 'pynput.keyboard._win32', 'pynput.mouse._win32', 'netifaces', 'zeroconf'
    ],
    excludes=['tkinter', 'PyQt5', 'matplotlib', 'PySide2', 'PySide6'],
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
    icon='6-phone-cat_icon-icons.com_76682.ico' if os.path.exists('6-phone-cat_icon-icons.com_76682.ico') else None,
)