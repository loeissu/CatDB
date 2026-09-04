# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_dynamic_libs, collect_data_files
block_cipher = None

# pywebview 自带的原生 DLL（WebView2Loader / WinForms 互操作）与 js/dom 资源
# 必须显式收集，否则冻结后的 EXE 无法创建桌面窗口
webview_binaries = collect_dynamic_libs('webview')
webview_datas = collect_data_files('webview')

a = Analysis(
    ['server.py'],
    pathex=[],
    binaries=webview_binaries,
    # www/（页面资源）+ cat_icon.ico（托盘图标与 EXE 同款）
    datas=[('www', 'www'), ('cat_icon.ico', '.')] + webview_datas,
    hiddenimports=[
        'webview', 'webview.platforms.edgechromium', 'webview.platforms.winforms', 'webview.platforms.mshtml',
        'pystray', 'pystray._win32',
        'aiohttp', 'aiohttp.web',
        'qrcode', 'PIL',
        'pyautogui', 'pynput', 'pynput.keyboard._win32', 'pynput.mouse._win32', 'netifaces', 'zeroconf', 'zeroconf.asyncio'
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
    icon='cat_icon.ico' if os.path.exists('cat_icon.ico') else None,
)