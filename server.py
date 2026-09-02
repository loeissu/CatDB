#!/usr/bin/env python3
"""
手机语音输入 → 电脑实时上屏（豆包喵喵·精调修正版）
UI变更：精致胡须、紧凑行距、猫咪下移、字体沉底
"""

import asyncio
import socket
import json
import platform
import sys
import threading
import time
import logging
import argparse
from aiohttp import web
import aiohttp
import pyautogui
import pyperclip
import subprocess

# 兼容 Windows 打包后控制台默认 GBK 编码，避免输出 emoji 时 UnicodeEncodeError
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger('catdb')

# 剪贴板操作锁
clipboard_lock = threading.Lock()

# ============== 配置项 ==============
CONFIG = {
    'port': 5000,
    'hotkey': 'f9',
}
# ===================================

def parse_args():
    parser = argparse.ArgumentParser(description='豆包喵喵 - 手机语音输入 → 电脑实时上屏')
    parser.add_argument('--port', type=int, default=5000, help='服务端口 (默认: 5000)')
    parser.add_argument('--hotkey', type=str, default='f9', help='清空快捷键 (默认: f9)')
    args = parser.parse_args()
    CONFIG['port'] = args.port
    CONFIG['hotkey'] = args.hotkey

pyautogui.PAUSE = 0
pyautogui.FAILSAFE = False  # 远程触控板控制场景，禁用左上角安全保护（否则移动到角落会抛异常）
connected_clients = set()
client_configs = {}
synced_text = ""
main_loop = None
typing_in_progress = False
rebase_triggered = False  # 标记是否已触发增量模式，避免重复触发
pending_strip_punctuation = False  # 标记下次输入是否需要去除开头标点

# 系统托盘相关
tray_icon = None
qr_window = None
search_status = "searching"  # searching / connected / qr_showed
search_start_time = None
QR_TIMEOUT = 10  # 10秒后显示二维码

# 切换窗口（Alt+Tab 连续切换）状态：按住 Alt 保持 1 秒，期间再次触发只按 Tab
hotkey_alt_held = False
hotkey_alt_timer = None
hotkey_alt_lock = threading.Lock()

# 核心 HTML/CSS 代码
HTML_PAGE = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
    <title>豆包喵喵</title>
    <link href="https://fonts.googleapis.com/css2?family=ZCOOL+KuaiLe&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #FFF9F0;
            --card-bg: #FFFFFF;
            --text-main: #5D4037;
            --text-light: #8D6E63;
            --accent-orange: #FFB74D;
            --accent-red: #FF8A65;
            --btn-bg: #FFFFFF;
            --line-color: #FBE9E7;
            /* 调整项：更密的行高，更小的顶部留白 */
            --line-height: 36px;
            --header-height: 40px; 
        }

        * { box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }
        
        body {
            font-family: 'ZCOOL KuaiLe', cursive, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-main);
            height: 100vh;
            display: flex;
            flex-direction: column;
            /* 底部留白：压缩hotkey bar高度后同步缩减，保持不遮挡主内容 */
            padding: 12px 14px calc(68px + env(safe-area-inset-bottom));
            overflow: hidden;
        }

        /* === 顶部栏 === */
        .header {
            display: flex;
            justify-content: space-between;
            align-items: flex-end;
            padding-bottom: 5px;
            /* 减少底部 margin，因为我们在 control-area 加了 margin-top */
            margin-bottom: 0px; 
        }

        .brand-container { width: 100px; display: flex; justify-content: center; }
        .brand {
            font-size: 26px;
            display: flex; align-items: center;
            text-shadow: 2px 2px 0px rgba(93, 64, 55, 0.15);
            line-height: 1; white-space: nowrap;
        }

        .status-container { width: 100px; display: flex; justify-content: center; }
        .status-badge {
            font-size: 13px; padding: 4px 10px; border-radius: 14px;
            background: #EFEBE9; color: var(--text-light);
            line-height: 1.2; display: flex; align-items: center;
            box-shadow: inset 0 2px 5px rgba(0,0,0,0.03); white-space: nowrap;
        }
        .status-badge.connected { background: #C8E6C9; color: #2E7D32; }
        .status-badge.disconnected { background: #FFCDD2; color: #C62828; }

        /* 浮动气泡 */
        .help-bubble {
            background: #fff; border: 2px solid #EFEBE9;
            padding: 5px 14px; border-radius: 20px;
            font-size: 13px; color: var(--text-light);
            cursor: pointer; position: relative; bottom: 2px;
            box-shadow: 0 3px 0 #D7CCC8;
            animation: float 3s ease-in-out infinite; 
        }
        .help-bubble:active { transform: translateY(3px); box-shadow: none; animation: none; }
        .help-bubble::after {
            content: ''; position: absolute; bottom: -6px; left: 50%; margin-left: -5px;
            width: 0; height: 0; border-left: 5px solid transparent; border-right: 5px solid transparent; border-top: 6px solid #EFEBE9;
        }
        .help-bubble::before {
            content: ''; position: absolute; bottom: -3px; left: 50%; margin-left: -3px;
            width: 0; height: 0; border-left: 3px solid transparent; border-right: 3px solid transparent; border-top: 4px solid #fff; z-index: 1;
        }
        @keyframes float { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-5px); } }

        /* === 核心控制区 === */
        .control-area {
            display: flex; justify-content: space-between; align-items: flex-end;
            /* 按钮自身上移后，control-area 的负 margin 略回收，让猫咪爪子仍精准扒在纸卡上 */
            margin-bottom: -18px; 
            position: relative; z-index: 10; padding: 0 4px;
            /* 顶部间距进一步压缩，让按钮贴"豆包喵喵"下方 */
            margin-top: 0px; 
        }

        .capsule-btn {
            background: var(--btn-bg); border: 2px solid #EFEBE9; color: var(--text-main);
            height: 48px; width: 100px; border-radius: 24px;
            display: flex; align-items: center; justify-content: center;
            gap: 6px; font-size: 17px; font-family: inherit;
            box-shadow: 0 4px 0 #D7CCC8; cursor: pointer;
            /* top 负值越小（越接近0）按钮越靠下。-42 → -34：向下落 8px。 */
            margin-bottom: 0px; transition: all 0.1s;
            position: relative; top: -34px;
        }
        .capsule-btn:active { transform: translateY(4px); box-shadow: none; }
        .capsule-btn.clear { background: var(--accent-orange); color: #fff; border-color: #FFA726; box-shadow: 0 4px 0 #EF6C00; }
        .capsule-btn.clear:active { box-shadow: none; }

        /* === 猫猫容器 === */
        .cat-wrapper {
            width: 130px; height: 85px;
            position: relative; display: flex; justify-content: center; align-items: flex-end;
            transform-origin: bottom center;
            transform: scale(1.25);
            /* 按钮上移后，微调猫咪向下保持爪子仍扒在纸卡顶部边缘 */
            margin-bottom: 8px;
        }

        .cat-head {
            width: 90px; height: 60px; background: var(--text-main);
            border-radius: 45px 45px 35px 35px; position: relative; z-index: 5;
        }
        .cat-ear {
            width: 0; height: 0;
            border-left: 14px solid transparent;
            border-right: 14px solid transparent;
            border-bottom: 22px solid var(--text-main);
            position: absolute; top: -14px;
        }
        .cat-ear.left { left: 6px; transform: rotate(-20deg); }
        .cat-ear.right { right: 6px; transform: rotate(20deg); }
        /* 耳朵内部粉色 */
        .cat-ear::after {
            content: '';
            position: absolute;
            top: 6px; left: -5px;
            border-left: 5px solid transparent;
            border-right: 5px solid transparent;
            border-bottom: 10px solid #FFAB91;
        }

        .cat-face {
            position: absolute; top: 20px; left: 50%; transform: translateX(-50%);
            display: flex; flex-direction: column; align-items: center; width: 100%;
        }
        .eyes-row { display: flex; gap: 24px; }
        .cat-eye {
            width: 10px; height: 10px;
            background: #fff;
            border-radius: 50%;
            animation: blink 4s infinite;
            box-shadow: inset 0 0 2px rgba(0,0,0,0.2);
        }
        .cat-nose {
            width: 10px; height: 7px;
            background: var(--accent-red);
            border-radius: 50% 50% 50% 50% / 30% 30% 70% 70%;
            margin-top: 6px;
        }

        /* 胡须 */
        .whiskers {
            position: absolute;
            top: 30px;
            left: 50%;
            transform: translateX(-50%);
            width: 90px;
            height: 16px;
        }

        .whisker {
            position: absolute;
            height: 1px;
            background: rgba(255,255,255,0.85);
        }

        /* 左侧胡须 */
        .whisker.left-1 { width: 28px; left: 0; top: 3px; transform: rotate(10deg); transform-origin: right center; }
        .whisker.left-2 { width: 28px; left: 0; top: 11px; transform: rotate(-10deg); transform-origin: right center; }

        /* 右侧胡须 */
        .whisker.right-1 { width: 28px; right: 0; top: 3px; transform: rotate(-10deg); transform-origin: left center; }
        .whisker.right-2 { width: 28px; right: 0; top: 11px; transform: rotate(10deg); transform-origin: left center; }

        .cat-paw {
            width: 26px; height: 18px; background: #FFF8E1;
            border-radius: 13px 13px 8px 8px;
            border: 2px solid var(--text-main); border-bottom: none;
            position: absolute; bottom: 0; z-index: 20;
            box-shadow: 0 2px 4px rgba(0,0,0,0.12);
        }
        .cat-paw.left { left: 22px; }
        .cat-paw.right { right: 22px; }
        /* 肉垫 */
        .cat-paw::before {
            content: '';
            position: absolute;
            top: 4px; left: 50%; transform: translateX(-50%);
            width: 8px; height: 6px;
            background: #FFCCBC;
            border-radius: 50%;
        }

        .typing .cat-paw.left { animation: tap 0.15s infinite alternate; }
        .typing .cat-paw.right { animation: tap 0.15s infinite alternate-reverse; }
        @keyframes tap { to { transform: translateY(6px); } }
        @keyframes blink { 0%,96%,100%{transform:scaleY(1)} 98%{transform:scaleY(0.1)} }

        /* === 便签纸 === */
        .paper-card {
            flex: 1;
            background: var(--card-bg);
            border-radius: 20px;
            box-shadow: 0 4px 15px rgba(93,64,55,0.08);
            border: 4px solid #EFEBE9;
            display: flex; flex-direction: column;
            /* 顶部加6px内边距，内容区远离圆角裁切边界，防止textarea渐变背景在圆角抗锯齿边缘形成白色尖角 */
            padding: 6px 4px 10px;
            position: relative; z-index: 1;
            /* 裁剪子元素到圆角内，避免textarea顶部白色渐变带盖住圆角边框形成尖角 */
            overflow: hidden;
            /* iOS Safari专用：确保圆角裁切同时作用于背景与内容 */
            isolation: isolate;
            -webkit-backface-visibility: hidden;
                    backface-visibility: hidden;
        }

        textarea {
            flex: 1; width: 100%; border: none; outline: none; resize: none;
            background: transparent;
            font-family: 'ZCOOL KuaiLe', cursive;
            font-size: 22px; /* 字体稍微减小以匹配密行距 */
            color: var(--text-main);
            line-height: var(--line-height);
            padding: 0 16px;
            
            /* 顶部留白：paper-card已加6px顶部内边距，因此此处相应减小6px，保持与原总留白一致 */
            padding-top: calc(var(--header-height) - 6px);
            
            background-image: 
                linear-gradient(to bottom, var(--card-bg) calc(var(--header-height) - 6px), transparent calc(var(--header-height) - 6px)),
                repeating-linear-gradient(
                    transparent,
                    transparent calc(var(--line-height) - 1px),
                    var(--line-color) calc(var(--line-height) - 1px),
                    var(--line-color) var(--line-height)
                );
            
            background-attachment: local;
            /* 调整背景线：让线位于行高偏下的位置，从而让文字看起来贴着线 */
            background-position: 0 -4px; 
            caret-color: var(--text-main);
        }
        textarea::placeholder { color: #D7CCC8; font-size: 20px; }

        .info-bar {
            text-align: right; padding: 5px 16px 0; font-size: 12px; color: #BCAAA4;
            display: flex; justify-content: space-between;
        }
        /* 触控板手势说明：默认隐藏，触控板展开时显示在底部左侧 */
        #tpHint { display: none; color: var(--text-light); font-size: 12px; }
        .tp-pad.open ~ .info-bar #tpHint { display: inline; }
        .tp-pad.open ~ .info-bar #timer { display: none; }

        /* 弹窗通用 */
        .modal-overlay {
            position: fixed; top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(93, 64, 55, 0.4); z-index: 999;
            display: none; align-items: center; justify-content: center; backdrop-filter: blur(2px);
        }
        .modal {
            background: #fff; width: 85%; max-width: 320px;
            border-radius: 24px; padding: 24px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.15);
            animation: popUp 0.3s cubic-bezier(0.18, 0.89, 0.32, 1.28);
        }
        @keyframes popUp { from{transform: scale(0.8); opacity:0} to{transform: scale(1); opacity:1} }
        
        .setting-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; font-size: 16px; }
        .setting-input { width: 70px; padding: 6px; border: 2px solid #EFEBE9; border-radius: 8px; text-align: center; font-family: inherit; font-size: 16px; color: var(--text-main); }
        .modal-btn { width: 100%; padding: 10px; background: var(--accent-orange); color: #fff; border: none; border-radius: 12px; font-family: inherit; font-size: 16px; margin-top: 10px; }
        /* 弹窗内容过长时可滚动 */
        .modal { max-height: 88vh; overflow-y: auto; }

        /* === 底部自定义快捷键栏 === */
        .hotkey-bar {
            position: fixed; bottom: 0; left: 0; right: 0;
            display: flex; align-items: center; gap: 6px;
            background: rgba(255, 249, 240, 0.92);
            border-top: 2px solid #EFEBE9;
            /* 压缩上下留白：top 10→5px, bottom 12→7px(=shadow3px+margin2px+safe区过渡) */
            padding: 5px 10px calc(7px + env(safe-area-inset-bottom)); z-index: 500;
            backdrop-filter: blur(4px); -webkit-backdrop-filter: blur(4px);
        }
        .hotkey-scroll {
            flex: 1; min-width: 0;
            display: flex; align-items: center; gap: 6px;
            overflow-x: auto; white-space: nowrap;
            scrollbar-width: none; -ms-overflow-style: none;
            /* 压缩内边距：仍保留 2px top / 6px bottom 以容纳按钮阴影(3px)和按下位移(3px) */
            padding: 2px 0 6px;
        }
        .hotkey-scroll::-webkit-scrollbar { display: none; }
        .hotkey-chip {
            flex-shrink: 0;
            display: inline-flex; align-items: center; gap: 3px;
            /* 缩紧内部 padding：上下 8→6px，左右 14→12px */
            padding: 6px 12px; border-radius: 18px;
            background: #fff; border: 2px solid #EFEBE9;
            box-shadow: 0 3px 0 #D7CCC8;
            /* 字号略小：15→14，与压缩后的高度匹配 */
            font-family: inherit; font-size: 14px; color: var(--text-main);
            cursor: pointer; transition: all 0.1s;
        }
        .hotkey-chip:active { transform: translateY(3px); box-shadow: none; }
        .hotkey-add {
            /* 加号按钮也略缩小：38→34px */
            flex-shrink: 0; width: 34px; height: 34px; border-radius: 50%;
            background: var(--accent-orange); color: #fff; border: none;
            font-size: 18px; line-height: 1; cursor: pointer;
            box-shadow: 0 3px 0 #EF6C00; transition: all 0.1s;
        }
        .hotkey-add:active { transform: translateY(3px); box-shadow: none; }

        /* 设置弹窗快捷键管理区 */
        .hk-section { margin-top: 20px; border-top: 2px dashed #FBE9E7; padding-top: 12px; }
        .hk-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; font-size: 15px; }
        .hk-add-btn {
            background: var(--accent-orange); color: #fff; border: none;
            border-radius: 14px; padding: 5px 12px; font-family: inherit; font-size: 13px; cursor: pointer;
            box-shadow: 0 2px 0 #EF6C00;
        }
        .hk-add-btn:active { transform: translateY(2px); box-shadow: none; }
        .hk-item {
            display: flex; align-items: center; gap: 8px;
            background: #FFF9F0; border: 2px solid #FBE9E7; border-radius: 12px;
            padding: 8px 10px; margin-bottom: 8px;
        }
        .hk-item-icon { font-size: 18px; }
        .hk-item-info { flex: 1; min-width: 0; }
        .hk-item-name { font-size: 14px; }
        .hk-locked { font-size: 10px; color: #A1887F; border: 1px solid #D7CCC8; border-radius: 6px; padding: 0 4px; margin-left: 6px; font-style: normal; vertical-align: 1px; }
        .hk-item-desc { font-size: 11px; color: var(--text-light); }
        .hk-item-btn { border: none; background: transparent; font-size: 14px; cursor: pointer; padding: 4px 6px; border-radius: 8px; color: var(--text-light); }
        .hk-item-btn.del { color: #E57373; }
        .hk-item-btn:active { background: #FBE9E7; }
        .setting-input-wide { flex: 1; min-width: 0; padding: 6px 8px; border: 2px solid #EFEBE9; border-radius: 8px; font-family: inherit; font-size: 15px; color: var(--text-main); background: #fff; }
        .hk-empty { text-align: center; font-size: 12px; color: #BCAAA4; padding: 8px 0; }

        /* === 触控板 === */
        .tp-fab {
            /* bottom 从 34px 调到 18px：向纸卡底部再下挪约16px，避免看起来悬空在上方 */
            position: absolute; left: 10px; bottom: 18px; z-index: 5;
            width: 42px; height: 42px; border-radius: 50%;
            background: #fff; border: 2px solid #EFEBE9;
            box-shadow: 0 3px 0 #D7CCC8;
            font-size: 18px; line-height: 1; cursor: pointer;
            display: flex; align-items: center; justify-content: center;
        }
        .tp-fab:active { transform: translateY(3px); box-shadow: none; }
        .tp-pad { display: none; flex: 1; flex-direction: column; min-height: 0; }
        .tp-pad.open { display: flex; }
        .tp-header {
            display: flex; justify-content: space-between; align-items: center;
            padding: 6px 12px; font-size: 14px; color: var(--text-main);
        }
        .tp-header small { font-size: 10px; color: #BCAAA4; margin-left: 4px; }
        .tp-mini {
            width: 34px; height: 34px; border-radius: 50%;
            background: var(--accent-orange); color: #fff; border: none;
            font-size: 18px; line-height: 1; cursor: pointer; box-shadow: 0 3px 0 #EF6C00;
            flex-shrink: 0;
        }
        .tp-mini:active { transform: translateY(3px); box-shadow: none; }
        .tp-surface {
            flex: 1; margin: 0 12px; border-radius: 16px;
            background: #FFF3E0; border: 3px dashed #FFCC80;
            touch-action: none; user-select: none; -webkit-user-select: none;
            display: flex; align-items: center; justify-content: center;
        }
        .tp-surface.active { background: #FFE0B2; }
        .tp-hint { font-size: 14px; color: #BCAAA4; pointer-events: none; }
        .tp-footer {
            display: flex; justify-content: center; align-items: center; gap: 10px;
            padding: 8px 0; font-size: 14px; color: var(--text-main);
        }
        .tp-footer button {
            width: 32px; height: 32px; border-radius: 50%;
            border: 2px solid #EFEBE9; background: #fff; color: var(--text-main);
            font-size: 16px; line-height: 1; cursor: pointer; box-shadow: 0 2px 0 #D7CCC8;
        }
        .tp-footer button:active { transform: translateY(2px); box-shadow: none; }
        .tp-footer .tp-mini { background: var(--accent-orange); color: #fff; border: none; width: 34px; height: 34px; box-shadow: 0 3px 0 #EF6C00; }
    </style>
</head>
<body>
    <div class="header">
        <div class="brand-container">
            <div class="brand">豆包喵喵</div>
        </div>
        <div class="help-bubble" id="helpBtn">使用帮助?</div>
        <div class="status-container">
            <div class="status-badge disconnected" id="status">断开</div>
        </div>
    </div>

    <div class="control-area">
        <button class="capsule-btn" id="settingsBtn"><span>⚙️</span> 设置</button>
        
        <div class="cat-wrapper" id="catAnim">
            <div class="cat-head">
                <div class="cat-ear left"></div>
                <div class="cat-ear right"></div>
                <div class="cat-face">
                    <div class="eyes-row">
                        <div class="cat-eye"></div>
                        <div class="cat-eye"></div>
                    </div>
                    <div class="cat-nose"></div>
                </div>
                <!-- 胡须 -->
                <div class="whiskers">
                    <div class="whisker left-1"></div>
                    <div class="whisker left-2"></div>
                    <div class="whisker right-1"></div>
                    <div class="whisker right-2"></div>
                </div>
            </div>
            <div class="cat-paw left"></div>
            <div class="cat-paw right"></div>
        </div>

        <button class="capsule-btn clear" id="clearBtn"><span>🗑️</span> 清空</button>
    </div>

    <div class="paper-card">
        <button class="tp-fab" id="tpFab" title="触控板">🖱️</button>
        <textarea 
            id="input" 
            placeholder="点击这里，告诉猫猫你想写什么..."
            autocomplete="off" autocorrect="off" autocapitalize="off" spellcheck="false"
        ></textarea>
        <div class="tp-pad" id="tpPad">
            <div class="tp-header">
                <span>🖱️ 触控板</span>
            </div>
            <div class="tp-surface" id="tpSurface">
                <div class="tp-hint">在此滑动控制电脑鼠标</div>
            </div>
            <div class="tp-footer">
                <button class="tp-mini" id="tpMini" title="缩小">－</button>
                <span>灵敏度</span>
                <button id="tpSensDown">－</button>
                <span id="tpSensVal">1.5</span>
                <button id="tpSensUp">＋</button>
            </div>
        </div>
        <div class="info-bar">
            <span id="tpHint">单指移动·轻点·双击·双指滚动/右键·双击拖拽</span>
            <span id="timer"></span>
            <span id="stats">已同步 0 字</span>
        </div>
    </div>

    <!-- 底部自定义快捷键栏 -->
    <div class="hotkey-bar">
        <div class="hotkey-scroll" id="hotkeyScroll"></div>
        <button class="hotkey-add" id="hotkeyAddBtn">＋</button>
    </div>

    <!-- 弹窗部分 -->
    <div class="modal-overlay" id="settingsModal">
        <div class="modal">
            <h3 style="text-align:center; margin-bottom:20px;">⚙️ 喵喵设置</h3>
            <div class="setting-row">
                <span>发送延迟 (ms)</span>
                <input type="number" class="setting-input" id="debounceDelay" value="500" step="100">
            </div>
            <div class="setting-row">
                <span>自动清空 (s)</span>
                <input type="number" class="setting-input" id="autoClearDelay" value="0" placeholder="0禁用">
            </div>
            <div class="setting-row">
                <span>检测电脑键盘</span>
                <input type="checkbox" id="detectKeyboard" style="width:20px; height:20px;" checked>
            </div>
            <div class="hk-section">
                <div class="hk-header">
                    <span>⚡ 自定义快捷键</span>
                    <button class="hk-add-btn" id="hkAddBtn">＋ 添加</button>
                </div>
                <div id="hkList"><div class="hk-empty">暂无快捷键</div></div>
            </div>
            <button class="modal-btn" onclick="closeModal('settingsModal')">保存设置</button>
        </div>
    </div>

    <div class="modal-overlay" id="helpModal">
        <div class="modal">
            <h3 style="text-align:center; margin-bottom:15px;">📖 使用指南</h3>
            <ul style="padding-left: 20px; line-height: 1.6; font-size: 14px; color: var(--text-main);">
                <li style="margin-bottom:8px"><b>基本用法：</b>在横线纸上语音或打字，文字会实时“飞”到电脑光标处。</li>
                <li style="margin-bottom:8px"><b>如何清空：</b>手机点「清空」、按换行键，或电脑按 <b style="background:#eee;padding:0 4px;border-radius:4px">F9</b> 均可。</li>
                <li style="margin-bottom:8px"><b>电脑介入（智能续写）：</b><br>当你操作电脑（打字/点击）后，手机会自动“翻篇”，下次输入将作为新段落发送，<b>不会</b>修改你刚才在电脑上编辑的内容。</li>
                <li><b>设置小贴士：</b><br>
                    • <b>发送延迟</b>：语音输入建议设为 300ms 以上，让输入法有时间自动纠错。<br>
                    • <b>检测键盘</b>：开启后才能使用“电脑介入”功能。
                </li>
            </ul>
            <button class="modal-btn" onclick="closeModal('helpModal')">明白啦</button>
        </div>
    </div>

    <!-- 快捷键编辑弹窗 -->
    <div class="modal-overlay" id="editHotkeyModal">
        <div class="modal">
            <h3 style="text-align:center; margin-bottom:20px;" id="hkModalTitle">添加快捷键</h3>
            <div class="setting-row">
                <span>名称</span>
                <input type="text" class="setting-input-wide" id="hkName" placeholder="如：复制">
            </div>
            <div class="setting-row">
                <span>类型</span>
                <select id="hkType" class="setting-input-wide">
                    <option value="keys">按键组合</option>
                    <option value="action">内置动作</option>
                    <option value="script">启动脚本</option>
                </select>
            </div>
            <div class="setting-row" id="hkKeysRow">
                <span>按键</span>
                <input type="text" class="setting-input-wide" id="hkKeys" placeholder="如 ctrl+c">
            </div>
            <div class="setting-row" id="hkActionRow" style="display:none;">
                <span>动作</span>
                <select class="setting-input-wide" id="hkAction">
                    <option value="enter">回车</option>
                    <option value="clear">清空</option>
                    <option value="rebase">触发续写</option>
                </select>
            </div>
            <div class="setting-row" id="hkScriptRow" style="display:none;">
                <span>脚本</span>
                <input type="text" class="setting-input-wide" id="hkCmd" placeholder="如 notepad.exe">
            </div>
            <button class="modal-btn" id="hkSaveBtn">保存</button>
            <button class="modal-btn" style="background:#D7CCC8; box-shadow:0 4px 0 #BCAAA4;" onclick="closeModal('editHotkeyModal')">取消</button>
        </div>
    </div>

    <script>
        const input = document.getElementById('input');
        const status = document.getElementById('status');
        const stats = document.getElementById('stats');
        const timer = document.getElementById('timer');
        const catAnim = document.getElementById('catAnim');
        
        function openModal(id) { document.getElementById(id).style.display = 'flex'; }
        function closeModal(id) { document.getElementById(id).style.display = 'none'; }
        
        document.getElementById('settingsBtn').onclick = () => openModal('settingsModal');
        document.getElementById('helpBtn').onclick = () => openModal('helpModal');
        document.querySelectorAll('.modal-overlay').forEach(el => el.onclick = (e) => { if(e.target === el) closeModal(el.id); });
        document.getElementById('clearBtn').onclick = performClearWithBlur;

        const debounceDelayInput = document.getElementById('debounceDelay');
        const autoClearDelayInput = document.getElementById('autoClearDelay');
        const detectKeyboardInput = document.getElementById('detectKeyboard');

        function saveSettings() {
            localStorage.setItem('debounceDelay', debounceDelayInput.value);
            localStorage.setItem('autoClearDelay', autoClearDelayInput.value);
            localStorage.setItem('detectKeyboard', detectKeyboardInput.checked);
        }
        function loadSettings() {
            const s1 = localStorage.getItem('debounceDelay');
            const s2 = localStorage.getItem('autoClearDelay');
            const s3 = localStorage.getItem('detectKeyboard');
            if(s1) debounceDelayInput.value = s1;
            if(s2) autoClearDelayInput.value = s2;
            if(s3 !== null) detectKeyboardInput.checked = s3 === 'true';
        }
        [debounceDelayInput, autoClearDelayInput].forEach(el => el.addEventListener('change', saveSettings));
        detectKeyboardInput.addEventListener('change', () => {
            saveSettings();
            if(ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'config', detectKeyboard: detectKeyboardInput.checked }));
        });
        loadSettings();

        let ws = null, lastSentText = '', totalSent = 0, ignoreLength = 0;
        let debounceTimer = null, autoClearTimer = null, autoClearCountdown = 0;

        function connect() {
            const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
            ws = new WebSocket(`${protocol}//${location.host}/ws`);
            ws.onopen = () => {
                status.textContent = '已连接'; status.className = 'status-badge connected';
                ws.send(JSON.stringify({ type: 'config', detectKeyboard: detectKeyboardInput.checked }));
            };
            ws.onclose = () => {
                status.textContent = '断开重连中'; status.className = 'status-badge disconnected';
                setTimeout(connect, 2000);
            };
            ws.onerror = () => ws.close();
            ws.onmessage = (e) => {
                const data = JSON.parse(e.data);
                if(data.type === 'clear') performClear();
                else if(data.type === 'clear_with_blur') performClearWithBlur();
                else if(data.type === 'rebase') {
                    ignoreLength = input.value.length; lastSentText = ''; status.textContent = '电脑介入';
                    setTimeout(() => { if(ws.readyState===1) status.textContent='已连接'; }, 2000);
                }
            };
        }

        function performClear() {
            if(debounceTimer) clearTimeout(debounceTimer);
            sendTextDiff();
            input.value = ''; ignoreLength = 0; lastSentText = '';
            if(ws && ws.readyState===1) ws.send(JSON.stringify({ type: 'reset' }));
            if(autoClearTimer) { clearInterval(autoClearTimer); timer.textContent=''; }
        }

        function performClearWithBlur() {
            performClear(); input.blur();
            requestAnimationFrame(() => requestAnimationFrame(() => input.focus()));
        }

        input.addEventListener('input', () => {
            catAnim.classList.add('typing');
            // 输入法换行：视为发送，同步到电脑回车后立即清空手机输入框
            if (input.value.includes('\\n')) {
                catAnim.classList.remove('typing');
                performClear();
                return;
            }
            const delay = parseInt(debounceDelayInput.value) || 500;
            if(debounceTimer) clearTimeout(debounceTimer);
            debounceTimer = setTimeout(() => {
                sendTextDiff(); catAnim.classList.remove('typing');
            }, delay);
            
            const acDelay = parseInt(autoClearDelayInput.value) || 0;
            if(autoClearTimer) clearInterval(autoClearTimer);
            if(acDelay > 0 && input.value) {
                autoClearCountdown = acDelay; timer.textContent = `${autoClearCountdown}s后清空`;
                autoClearTimer = setInterval(() => {
                    autoClearCountdown--;
                    if(autoClearCountdown <= 0) { clearInterval(autoClearTimer); performClearWithBlur(); }
                    else timer.textContent = `${autoClearCountdown}s后清空`;
                }, 1000);
            } else timer.textContent = '';
        });

        function sendTextDiff() {
            const full = input.value;
            if(full.length < ignoreLength) ignoreLength = full.length;
            const effective = full.substring(ignoreLength);
            if(effective === lastSentText) return;
            if(ws && ws.readyState===1) {
                ws.send(JSON.stringify({ type: 'diff', oldText: lastSentText, newText: effective }));
                const diff = effective.length - lastSentText.length;
                if(diff > 0) totalSent += diff;
                stats.textContent = `已同步 ${totalSent} 字`;
                lastSentText = effective;
            }
        }

        // 注意：不拦截 Enter 按键，让输入法换行/回车正常插入换行符，
        // 由后端 diff 同步为电脑回车键（手机软键盘换行在部分平台会触发 keydown Enter）

        // ============ 自定义快捷键模块 ============
        const DEFAULT_HOTKEYS = [
            // 固定快捷键（切换窗口）：不可删除、不可编辑，始终排在首位
            { id: 'hk_switch', name: '切换窗口', icon: '🔄', type: 'keys', keys: 'alt+tab', locked: true },
            { id: 'hk1', name: 'Esc', icon: '⎋', type: 'keys', keys: 'esc' },
            { id: 'hk2', name: '全选', icon: '🔲', type: 'keys', keys: 'ctrl+a' },
            { id: 'hk3', name: '删除', icon: '🗑️', type: 'keys', keys: 'delete' },
            { id: 'hk4', name: '复制', icon: '📋', type: 'keys', keys: 'ctrl+c' },
            { id: 'hk5', name: '粘贴', icon: '📌', type: 'keys', keys: 'ctrl+v' },
        ];
        const hotkeyScroll = document.getElementById('hotkeyScroll');
        const hotkeyListEl = document.getElementById('hkList');
        const hotkeyBarEl = document.querySelector('.hotkey-bar');

        // 软键盘弹出时，将底部快捷键栏顶到输入法上方。
        // 平台差异：Android 浏览器(Chrome/Edge/默认浏览器)会自动把 fixed bottom 元素
        // 顶到键盘上方；只有 iOS Safari 会把 fixed 元素压在键盘下，需要手动顶起。
        const isIOS = /iPhone|iPad|iPod/i.test(navigator.userAgent) ||
                      (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
        function syncHotkeyBarPosition() {
            if (!window.visualViewport) return;
            const vv = window.visualViewport;
            if (isIOS && vv.height < window.innerHeight) {
                // iOS：键盘弹出时固定元素被压住，将 bottom 设为键盘高度顶到输入法上方
                const kbdHeight = window.innerHeight - vv.height - vv.offsetTop;
                hotkeyBarEl.style.bottom = Math.max(kbdHeight, 0) + 'px';
            } else {
                // Android/无键盘：fixed 元素已自动跟随可视区域，保持贴底
                hotkeyBarEl.style.bottom = '0px';
            }
        }
        if (window.visualViewport) {
            window.visualViewport.addEventListener('resize', syncHotkeyBarPosition);
            window.visualViewport.addEventListener('scroll', syncHotkeyBarPosition);
        }

        const HOTKEYS_VERSION = '5'; // 默认快捷键列表变更时递增，用于自动覆盖旧版默认数据
        function loadHotkeys() {
            const raw = localStorage.getItem('hotkeys');
            const ver = localStorage.getItem('hotkeys_version');
            let list;
            if (!raw || ver !== HOTKEYS_VERSION) {
                list = DEFAULT_HOTKEYS.slice();
            } else {
                try { list = JSON.parse(raw); } catch (e) { list = DEFAULT_HOTKEYS.slice(); }
            }
            // 迁移：输入法换行已自动映射为电脑回车，移除已废弃的「回车」动作项
            list = list.filter(h => !(h.type === 'action' && h.action === 'enter'));
            // 迁移：固定项（切换窗口）始终存在且置于首位，旧的同键项一并移除
            const locked = DEFAULT_HOTKEYS.find(h => h.locked);
            list = list.filter(h => !(h.locked || (h.type === 'keys' && h.keys === 'alt+tab')));
            if (locked) list.unshift({ ...locked });
            return list;
        }
        function saveHotkeys(list) {
            localStorage.setItem('hotkeys', JSON.stringify(list));
            localStorage.setItem('hotkeys_version', HOTKEYS_VERSION);
        }

        // 生成快捷键说明文案（用于设置列表展示）
        function hkDesc(item) {
            if (item.type === 'keys') return item.keys || '';
            if (item.type === 'action') return '动作:' + (item.action || '');
            return '脚本:' + (item.cmd || '');
        }

        // 渲染底部悬浮快捷键栏
        function renderHotkeys() {
            const list = loadHotkeys();
            hotkeyScroll.innerHTML = '';
            list.forEach(item => {
                const btn = document.createElement('button');
                btn.className = 'hotkey-chip';
                btn.innerHTML = `${item.icon || ''} ${item.name}`;
                btn.onclick = () => onHotkeyClick(item);
                hotkeyScroll.appendChild(btn);
            });
            renderHotkeyList(list);
        }

        // 点击快捷键：发送到电脑端执行
        function onHotkeyClick(item) {
            if (!ws || ws.readyState !== WebSocket.OPEN) { alert('未连接到电脑，请先连接'); return; }
            // 回车动作：电脑端按回车确认输入，同时清空手机端文字
            if (item.type === 'action' && item.action === 'enter') {
                performClearWithBlur();
            }
            ws.send(JSON.stringify({ type: 'shortcut', sc: item }));
            // 收起键盘，让用户看到电脑端执行效果后继续输入
            input.blur();
            requestAnimationFrame(() => requestAnimationFrame(() => input.focus()));
        }

        // 渲染设置弹窗内的快捷键列表
        function renderHotkeyList(list) {
            if (!list.length) { hotkeyListEl.innerHTML = '<div class="hk-empty">暂无快捷键，点击右上角添加</div>'; return; }
            hotkeyListEl.innerHTML = '';
            list.forEach((item, idx) => {
                const row = document.createElement('div');
                row.className = 'hk-item';
                const lockedTag = item.locked ? '<em class="hk-locked">固定</em>' : '';
                const actions = item.locked ? '' : `
                    <button class="hk-item-btn" data-act="edit">✏️</button>
                    <button class="hk-item-btn del" data-act="del">🗑️</button>`;
                row.innerHTML = `
                    <span class="hk-item-icon">${item.icon || '🔘'}</span>
                    <div class="hk-item-info">
                        <div class="hk-item-name">${item.name}${lockedTag}</div>
                        <div class="hk-item-desc">${hkDesc(item)}</div>
                    </div>
                    ${actions}
                `;
                if (!item.locked) {
                    row.querySelector('[data-act="edit"]').onclick = () => openHkEditor(item);
                    row.querySelector('[data-act="del"]').onclick = () => {
                        list.splice(idx, 1);
                        saveHotkeys(list);
                        renderHotkeys();
                    };
                }
                hotkeyListEl.appendChild(row);
            });
        }

        // ===== 添加快捷键弹窗逻辑 =====
        let editingHkId = null;
        function openHkEditor(item) {
            editingHkId = item ? item.id : null;
            document.getElementById('hkModalTitle').textContent = item ? '编辑快捷键' : '添加快捷键';
            document.getElementById('hkName').value = item ? (item.name || '') : '';
            document.getElementById('hkType').value = item ? item.type : 'keys';
            document.getElementById('hkKeys').value = item && item.keys ? item.keys : '';
            document.getElementById('hkAction').value = item && item.action ? item.action : 'enter';
            document.getElementById('hkCmd').value = item && item.cmd ? item.cmd : '';
            syncHkRows();
            openModal('editHotkeyModal');
        }
        // 根据类型切换显示对应的参数输入行
        function syncHkRows() {
            const t = document.getElementById('hkType').value;
            document.getElementById('hkKeysRow').style.display = t === 'keys' ? 'flex' : 'none';
            document.getElementById('hkActionRow').style.display = t === 'action' ? 'flex' : 'none';
            document.getElementById('hkScriptRow').style.display = t === 'script' ? 'flex' : 'none';
        }
        document.getElementById('hkType').addEventListener('change', syncHkRows);
        document.getElementById('hkSaveBtn').onclick = () => {
            const name = document.getElementById('hkName').value.trim();
            const type = document.getElementById('hkType').value;
            const keys = document.getElementById('hkKeys').value.trim();
            const action = document.getElementById('hkAction').value;
            const cmd = document.getElementById('hkCmd').value.trim();
            if (!name) { alert('请输入名称'); return; }
            if (type === 'keys' && !keys) { alert('请输入按键组合'); return; }
            if (type === 'script' && !cmd) { alert('请输入脚本命令'); return; }
            const list = loadHotkeys();
            if (editingHkId) {
                const idx = list.findIndex(i => i.id === editingHkId);
                if (idx >= 0) list[idx] = { ...list[idx], name, type, keys, action, cmd };
            } else {
                list.push({ id: 'hk' + Date.now(), name, type, keys, action, cmd, icon: type === 'keys' ? '⌨️' : (type === 'action' ? '⚡' : '📜') });
            }
            saveHotkeys(list);
            renderHotkeys();
            closeModal('editHotkeyModal');
        };
        document.getElementById('hkAddBtn').onclick = () => openHkEditor(null);
        document.getElementById('hotkeyAddBtn').onclick = () => { openModal('settingsModal'); openHkEditor(null); };
        renderHotkeys();

        // ============ 触控板模块 ============
        const tpFab = document.getElementById('tpFab');
        const tpPad = document.getElementById('tpPad');
        const tpSurface = document.getElementById('tpSurface');

        // 触控板展开/收起：占据输入区位置，底部快捷键栏不受影响
        function openTouchpad() {
            input.blur();
            tpFab.style.display = 'none';
            input.style.display = 'none';
            tpPad.classList.add('open');
        }
        function closeTouchpad() {
            tpPad.classList.remove('open');
            input.style.display = '';
            tpFab.style.display = '';
            requestAnimationFrame(() => requestAnimationFrame(() => input.focus()));
        }
        tpFab.addEventListener('click', openTouchpad);
        document.getElementById('tpMini').addEventListener('click', closeTouchpad);

        // 触控板灵敏度（存 localStorage）
        function tpSensitivity() { return parseFloat(localStorage.getItem('tpSensitivity')) || 2; }
        function renderTpSens() { document.getElementById('tpSensVal').textContent = tpSensitivity().toFixed(1); }
        document.getElementById('tpSensDown').addEventListener('click', () => {
            localStorage.setItem('tpSensitivity', Math.max(0.5, tpSensitivity() - 0.5).toFixed(1));
            renderTpSens();
        });
        document.getElementById('tpSensUp').addEventListener('click', () => {
            localStorage.setItem('tpSensitivity', Math.min(3, tpSensitivity() + 0.5).toFixed(1));
            renderTpSens();
        });
        renderTpSens();

        // 手势采集
        function sendTouch(action, extra) {
            if (!ws || ws.readyState !== WebSocket.OPEN) return;
            ws.send(JSON.stringify(Object.assign({ type: 'touch', action }, extra || {})));
        }
        let tpTouches = new Map();      // identifier -> {x, y}
        let tpMode = 'none';            // none | move | scroll
        let tpMoved = false;            // 单指是否产生位移（区分点击）
        let tpScrollMoved = false;      // 双指是否产生滚动（区分右键）
        let tpStartX = 0, tpStartY = 0; // 单指起始位置
        let tpLastTap = 0;              // 上次轻点时间（用于双击/拖拽判定）
        let tpDrag = false;             // 是否处于拖拽模式（双击第二按按住不放）
        let tpPendingMove = null;       // 累积待发送位移
        let tpRafId = null;

        // rAF 节流发送：合并一帧内的位移
        function tpFlushMove() {
            tpRafId = null;
            if (tpPendingMove && (tpPendingMove.dx || tpPendingMove.dy)) {
                const sens = tpSensitivity();
                sendTouch(tpDrag ? 'drag_move' : 'move', { dx: Math.round(tpPendingMove.dx * sens), dy: Math.round(tpPendingMove.dy * sens) });
                tpPendingMove = null;
            }
        }
        function tpScheduleMove(dx, dy) {
            if (!tpPendingMove) tpPendingMove = { dx: 0, dy: 0 };
            tpPendingMove.dx += dx;
            tpPendingMove.dy += dy;
            if (!tpRafId) tpRafId = requestAnimationFrame(tpFlushMove);
        }

        tpSurface.addEventListener('touchstart', (e) => {
            e.preventDefault();
            tpSurface.classList.add('active');
            tpTouches.clear();
            for (let i = 0; i < e.touches.length; i++) tpTouches.set(e.touches[i].identifier, { x: e.touches[i].clientX, y: e.touches[i].clientY });
            if (e.touches.length === 1) {
                const now = Date.now();
                // 双击第二按（距上次轻点 < 300ms）→ 进入拖拽模式，按住左键
                if (tpLastTap && now - tpLastTap < 300) {
                    tpDrag = true;
                    sendTouch('drag_start');
                } else {
                    tpDrag = false;
                }
                tpLastTap = 0;
                tpMode = 'move';
                tpMoved = false;
                tpStartX = e.touches[0].clientX;
                tpStartY = e.touches[0].clientY;
            } else if (e.touches.length === 2) {
                tpMode = 'scroll';
                tpScrollMoved = false;
            }
        }, { passive: false });

        tpSurface.addEventListener('touchmove', (e) => {
            e.preventDefault();
            // 单指变双指：切换到滚动模式
            if (e.touches.length === 2 && tpMode !== 'scroll') {
                tpMode = 'scroll';
                tpScrollMoved = false;
                tpTouches.clear();
                for (let i = 0; i < e.touches.length; i++) tpTouches.set(e.touches[i].identifier, { x: e.touches[i].clientX, y: e.touches[i].clientY });
                return;
            }
            if (tpMode === 'move' && e.touches.length === 1) {
                const p = e.touches[0];
                const prev = tpTouches.get(p.identifier);
                if (!prev) return;
                const dx = p.clientX - prev.x;
                const dy = p.clientY - prev.y;
                tpTouches.set(p.identifier, { x: p.clientX, y: p.clientY });
                if (Math.abs(p.clientX - tpStartX) > 8 || Math.abs(p.clientY - tpStartY) > 8) tpMoved = true;
                tpScheduleMove(dx, dy);
            } else if (tpMode === 'scroll') {
                // 双指垂直平均位移换算滚轮格数：双指上滑(dy负) → 内容向上滚动(正)
                let totalDy = 0, cnt = 0;
                for (let i = 0; i < e.touches.length; i++) {
                    const p = e.touches[i];
                    const prev = tpTouches.get(p.identifier);
                    if (prev) { totalDy += p.clientY - prev.y; cnt++; }
                    tpTouches.set(p.identifier, { x: p.clientX, y: p.clientY });
                }
                if (cnt) {
                    const units = Math.round(-(totalDy / cnt) / 10);
                    if (units) { tpScrollMoved = true; sendTouch('scroll', { dy: units }); }
                }
            }
        }, { passive: false });

        tpSurface.addEventListener('touchend', (e) => {
            e.preventDefault();
            tpSurface.classList.remove('active');
            if (tpMode === 'move' && e.touches.length === 0) {
                if (tpDrag) {
                    // 先 flush 残余拖拽位移（保持 drag_move），再松开左键
                    if (tpRafId) { cancelAnimationFrame(tpRafId); tpRafId = null; tpFlushMove(); }
                    sendTouch('drag_end');
                    tpDrag = false;
                } else {
                    if (!tpMoved) {
                        const now = Date.now();
                        if (now - tpLastTap < 300) { sendTouch('double_tap'); tpLastTap = 0; }
                        else { tpLastTap = now; sendTouch('tap'); }
                    }
                    if (tpRafId) { cancelAnimationFrame(tpRafId); tpRafId = null; tpFlushMove(); }
                }
                tpMode = 'none';
                tpTouches.clear();
            } else if (tpMode === 'scroll' && e.touches.length < 2) {
                // 双指结束：全程无滚动则判定为右键
                if (!tpScrollMoved) sendTouch('right_tap');
                tpMode = 'none';
                tpTouches.clear();
                tpScrollMoved = false;
            }
        }, { passive: false });

        tpSurface.addEventListener('touchcancel', () => {
            tpSurface.classList.remove('active');
            if (tpDrag) { sendTouch('drag_end'); tpDrag = false; }
            tpMode = 'none';
            tpTouches.clear();
            if (tpRafId) { cancelAnimationFrame(tpRafId); tpRafId = null; }
        });

        connect();
        // 首次访问页面自动聚焦输入框，尽量直接唤起手机输入法
        window.onload = () => {
            setTimeout(() => { try { input.focus(); } catch(e) {} }, 100);
            // iOS 等平台禁止脚本自动弹键盘，改为用户首次触摸页面任意处时聚焦唤起
            document.addEventListener('touchstart', () => { try { input.focus(); } catch(e) {} }, { once: true });
        };
    </script>
</body>
</html>
'''

def get_local_ip():
    try:
        hostname = socket.gethostname()
        ips = socket.gethostbyname_ex(hostname)[2]
        for ip in ips:
            if ip.startswith('192.168.') or ip.startswith('10.'): return ip
        for ip in ips:
            if ip.startswith('172.') and 16 <= int(ip.split('.')[1]) <= 31: return ip
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]; s.close()
        return ip
    except: return '127.0.0.1'

def compute_diff(old, new):
    if old == new:
        return 0, ''
    # 找到共同前缀长度
    prefix = 0
    for i in range(min(len(old), len(new))):
        if old[i] == new[i]:
            prefix += 1
        else:
            break
    # 找到共同后缀长度（从前缀结束后开始）
    suffix = 0
    old_tail = old[prefix:]
    new_tail = new[prefix:]
    for i in range(min(len(old_tail), len(new_tail))):
        if old_tail[-(i+1)] == new_tail[-(i+1)]:
            suffix += 1
        else:
            break
    # 需要删除的字符数 = 旧文本中除去前后缀的部分
    del_count = len(old) - prefix - suffix
    # 需要添加的文本 = 新文本中除去前后缀的部分
    add_text = new[prefix:len(new)-suffix]
    return del_count, add_text

def type_text(text):
    """
    将文本输入到电脑当前焦点处（文本段走剪贴板粘贴，换行符 \n 映射为回车键）。
    参数 text: 要输入的文本，可包含换行。
    返回 None。
    """
    global typing_in_progress
    if not text: return
    release_alt()  # 输入文字前先释放保持中的 Alt，避免 Alt 与 Ctrl+V 组合造成干扰
    typing_in_progress = True
    try:
        # 按换行拆分，段间用回车键衔接，避免剪贴板粘贴 \n 在目标程序中失效
        segments = text.split('\n')
        for i, seg in enumerate(segments):
            if seg:
                with clipboard_lock:
                    try: orig = pyperclip.paste()
                    except: orig = ''
                    pyperclip.copy(seg)
                    if platform.system() == 'Darwin': pyautogui.hotkey('command', 'v')
                    else: pyautogui.hotkey('ctrl', 'v')
                    time.sleep(0.1)
                    try: pyperclip.copy(orig)
                    except: pass
            if i < len(segments) - 1:
                pyautogui.press('enter')
                time.sleep(0.05)
    finally: typing_in_progress = False

def switch_window():
    """
    执行切换窗口（Alt+Tab 连续切换）。
    首次按住 Alt 并按 Tab；1 秒内再次触发只按 Tab 切到下一个窗口，超时自动释放 Alt。
    返回 True 表示执行成功。
    """
    global hotkey_alt_held, hotkey_alt_timer, typing_in_progress
    with hotkey_alt_lock:
        # 取消上一次的自动释放定时器，重新计时 1 秒
        if hotkey_alt_timer:
            hotkey_alt_timer.cancel()
        typing_in_progress = True
        try:
            if not hotkey_alt_held:
                pyautogui.keyDown('alt')
                hotkey_alt_held = True
            pyautogui.press('tab')
        finally:
            typing_in_progress = False
        hotkey_alt_timer = threading.Timer(1.0, release_alt)
        hotkey_alt_timer.daemon = True
        hotkey_alt_timer.start()
    return True

def release_alt():
    """
    释放保持中的 Alt 键（1 秒无后续切换时由定时器触发，或执行其他动作前主动调用）。
    返回 None。
    """
    global hotkey_alt_held, hotkey_alt_timer
    with hotkey_alt_lock:
        if hotkey_alt_held:
            try:
                pyautogui.keyUp('alt')
            except Exception as e:
                print(f'⚠️ 释放 Alt 失败: {e}')
            hotkey_alt_held = False
        hotkey_alt_timer = None

def execute_shortcut(sc):
    """
    执行手机端发送的自定义快捷键动作。
    参数 sc: 前端传来的快捷键对象 {type: 'keys'|'action'|'script', keys/action/cmd}。
    返回 True 表示执行成功，False 表示参数无效或执行失败。
    """
    stype = sc.get('type')
    try:
        if stype == 'keys':
            # 按键组合：如 'ctrl+s'，用 + 分隔各部分
            parts = [p.strip().lower() for p in sc.get('keys', '').split('+') if p.strip()]
            if not parts:
                return False
            if len(parts) == 2 and 'alt' in parts and 'tab' in parts:
                # 切换窗口：按住 Alt 保持 1 秒，期间再次触发只按 Tab 连续切换
                switch_window()
            elif len(parts) == 1:
                release_alt()  # 单键操作前先释放保持中的 Alt
                pyautogui.press(parts[0])
            else:
                release_alt()  # 其他组合键操作前先释放保持中的 Alt
                pyautogui.hotkey(*parts)
        elif stype == 'action':
            release_alt()  # 执行动作前先释放保持中的 Alt
            action = sc.get('action')
            if action == 'enter':
                pyautogui.press('enter')
            elif action == 'clear':
                reset_synced_text()
                return True
            elif action == 'rebase':
                if main_loop:
                    asyncio.run_coroutine_threadsafe(broadcast_rebase(), main_loop)
                return True
            else:
                return False
        elif stype == 'script':
            release_alt()  # 启动脚本前先释放保持中的 Alt
            # 启动电脑本机命令/脚本（局域网个人工具，与现有热键同信任模型）
            cmd = sc.get('cmd', '').strip()
            if not cmd:
                return False
            subprocess.Popen(cmd, shell=True)
        else:
            return False
        # 按键类操作属于“电脑介入”，触发增量模式，避免与手机端输入冲突
        if any(c.get('detect_keyboard') for c in client_configs.values()):
            reset_synced_text()
        return True
    except Exception as e:
        print(f'⚠️ 快捷键执行失败: {e}')
        return False

# 触控板虚拟鼠标位置：累积增量做绝对定位，规避 Windows 高频 SetCursorPos 后读取位置滞后导致的“抖动不移动”
touchpad_pos = None

def move_cursor_by(dx, dy):
    """
    按增量移动鼠标：基于虚拟位置累积做绝对定位，避免每次读实际光标位置造成位移抵消。
    参数 dx/dy: 相对位移（像素）。
    """
    global touchpad_pos
    if dx == 0 and dy == 0:
        return
    if touchpad_pos is None:
        touchpad_pos = pyautogui.position()
    sw, sh = pyautogui.size()
    tx = min(max(0, touchpad_pos[0] + dx), sw - 1)
    ty = min(max(0, touchpad_pos[1] + dy), sh - 1)
    touchpad_pos = (tx, ty)
    pyautogui.moveTo(tx, ty)

def handle_touch(msg):
    """
    执行手机端触控板发送的触摸动作。
    参数 msg: 前端传来的触控消息 {action, dx, dy}（dx/dy 已按灵敏度换算）。
    返回 True 表示执行成功，False 表示参数无效或执行失败。
    """
    global touchpad_pos
    action = msg.get('action')
    try:
        if action == 'move':
            move_cursor_by(msg.get('dx', 0), msg.get('dy', 0))
        elif action == 'tap':
            touchpad_pos = None  # 点击后重新同步实际位置
            pyautogui.click()
        elif action == 'double_tap':
            touchpad_pos = None
            pyautogui.doubleClick()
        elif action == 'right_tap':
            touchpad_pos = None
            pyautogui.rightClick()
        elif action == 'scroll':
            pyautogui.scroll(msg.get('dy', 0))
        elif action == 'drag_start':
            touchpad_pos = None  # 按下前重新同步实际位置
            pyautogui.mouseDown()
        elif action == 'drag_move':
            move_cursor_by(msg.get('dx', 0), msg.get('dy', 0))
        elif action == 'drag_end':
            touchpad_pos = None  # 松开后重新同步实际位置
            pyautogui.mouseUp()
        else:
            return False
        return True
    except Exception as e:
        print(f'⚠️ 触控执行失败: {e}')
        return False

def send_backspaces(count):
    global typing_in_progress
    if count <= 0: return
    release_alt()  # 回退输入前先释放保持中的 Alt，避免干扰组合键
    typing_in_progress = True
    try:
        for i in range(count):
            pyautogui.press('backspace')
            if i < count - 1: time.sleep(0.04)
    finally: typing_in_progress = False

async def handle_index(req):
    # 禁用缓存，避免浏览器缓存旧页面导致更新不生效
    return web.Response(text=HTML_PAGE, content_type='text/html', headers={'Cache-Control': 'no-store'})
async def handle_websocket(req):
    global synced_text
    ws = web.WebSocketResponse()
    await ws.prepare(req)
    connected_clients.add(ws)
    print('📱 手机已连接')
    try:
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                data = json.loads(msg.data)
                if data.get('type') == 'config':
                    client_configs[ws] = {'detect_keyboard': data.get('detectKeyboard')}
                elif data.get('type') == 'diff':
                    global rebase_triggered, pending_strip_punctuation
                    new_txt = data.get('newText', '')
                    d_cnt, add_txt = compute_diff(synced_text, new_txt)
                    # 触发增量/清空后，下一次无回退的输入才剪除句首标点
                    if pending_strip_punctuation and d_cnt == 0 and add_txt:
                        # 中英文常见标点符号（不含书名号、方括号等成对符号，但保留引号）
                        punctuations = "，。、；：？！""''·…—～,.;:?!'\""
                        if add_txt[0] in punctuations:
                            add_txt = add_txt[1:]  # 只剪除发送内容的标点
                            print(f'✂️ 去除开头标点')
                        pending_strip_punctuation = False  # 只处理一次
                    rebase_triggered = False  # 手机端有新输入，重置增量触发标志
                    if d_cnt: send_backspaces(d_cnt); print(f'⌫ {d_cnt}')
                    if add_txt: type_text(add_txt); print(f'⌨️ {add_txt!r}')
                    synced_text = new_txt
                elif data.get('type') == 'reset':
                    synced_text = ""
                    pending_strip_punctuation = True  # 清空后下次输入需要检查标点
                    print('🔄 重置')
                elif data.get('type') == 'shortcut':
                    # 手机端自定义快捷键：按键组合 / 内置动作 / 启动脚本
                    ok = execute_shortcut(data.get('sc') or {})
                    await ws.send_json({'type': 'shortcut_result', 'ok': ok})
                elif data.get('type') == 'touch':
                    # 手机端触控板：移动 / 点击 / 双击 / 右键 / 滚动
                    handle_touch(data)
    finally: connected_clients.discard(ws); client_configs.pop(ws, None); print('📱 断开')
    return ws

async def broadcast_clear_with_blur():
    for ws in list(connected_clients):
        try: await ws.send_json({'type': 'clear_with_blur'})
        except: pass

async def broadcast_rebase():
    for ws in list(connected_clients):
        try: await ws.send_json({'type': 'rebase'})
        except: pass

def reset_synced_text():
    global synced_text, rebase_triggered, pending_strip_punctuation
    if typing_in_progress: return
    if rebase_triggered: return  # 已触发过增量模式，等待手机端新输入后再允许触发
    if synced_text:
        synced_text = ""
        rebase_triggered = True  # 标记已触发
        pending_strip_punctuation = True  # 下次输入需要检查标点
        print('🔄 电脑端输入，触发增量同步')
        if main_loop: asyncio.run_coroutine_threadsafe(broadcast_rebase(), main_loop)

def setup_hotkey():
    global main_loop
    hotkey = CONFIG.get('hotkey', '').strip()
    IGNORED = {'shift','ctrl','alt','cmd','num_lock','scroll_lock','home','end','page_up','page_down','insert','escape','print_screen','pause','f1','f2','f3','f4','f5','f6','f7','f8','f9','f10','f11','f12'}
    try:
        from pynput import keyboard, mouse

        # 键盘监听
        def on_press(key):
            try:
                k = key.char if hasattr(key, 'char') else key.name
                if not k: return
                if hotkey and k.lower() == hotkey.lower():
                    if main_loop: asyncio.run_coroutine_threadsafe(broadcast_clear_with_blur(), main_loop)
                    return
                if k.lower() not in IGNORED and any(c.get('detect_keyboard') for c in client_configs.values()):
                    reset_synced_text()
            except: pass

        # 鼠标监听 - 左键点击触发增量模式
        def on_click(x, y, button, pressed):
            try:
                # 只在左键按下时触发，释放时不触发
                if button == mouse.Button.left and pressed:
                    if any(c.get('detect_keyboard') for c in client_configs.values()):
                        reset_synced_text()
            except: pass

        keyboard.Listener(on_press=on_press).start()
        mouse.Listener(on_click=on_click).start()
        if hotkey: print(f'🎹 热键: [{hotkey}]')
        print('🖱️ 鼠标左键监测已启用')
    except: print('⚠️  热键需安装 pynput')

async def handle_qr(req):
    try:
        import qrcode
        from io import BytesIO
        ip = get_local_ip()
        port = CONFIG.get('port', 5000)
        url = f'http://{ip}:{port}'
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color='black', back_color='white')
        buf = BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)
        return web.Response(body=buf.read(), content_type='image/png')
    except Exception as e:
        return web.Response(text=f'QR generation failed: {e}', status=500)

# ============== 系统托盘 + QR 窗口逻辑 ==============
def create_qr_image():
    """生成 QR 码的 PIL Image 对象"""
    try:
        import qrcode
        ip = get_local_ip()
        port = CONFIG.get('port', 5000)
        url = f'http://{ip}:{port}'
        qr = qrcode.QRCode(version=1, box_size=8, border=2)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color='black', back_color='white')
        return img
    except Exception as e:
        logger.error(f'生成二维码失败: {e}')
        return None

def show_qr_window():
    """显示二维码弹窗（在子线程中运行）"""
    global qr_window, search_status
    if qr_window is not None:
        return
    search_status = "qr_showed"
    
    try:
        import tkinter as tk
        from PIL import ImageTk
        
        qr_window = tk.Tk()
        qr_window.title('豆包喵喵 - 扫码连接')
        qr_window.resizable(False, False)
        qr_window.attributes('-topmost', True)
        
        # 窗口居中
        w, h = 320, 400
        sw = qr_window.winfo_screenwidth()
        sh = qr_window.winfo_screenheight()
        qr_window.geometry(f'{w}x{h}+{(sw-w)//2}+{(sh-h)//2}')
        
        # 标题
        title = tk.Label(qr_window, text='📱 使用手机扫描二维码连接', font=('微软雅黑', 12, 'bold'))
        title.pack(pady=(20, 10))
        
        # QR 码
        qr_img = create_qr_image()
        if qr_img:
            tk_img = ImageTk.PhotoImage(qr_img)
            qr_label = tk.Label(qr_window, image=tk_img)
            qr_label.image = tk_img  # 保持引用
            qr_label.pack(pady=10)
        
        # URL 显示
        ip = get_local_ip()
        port = CONFIG.get('port', 5000)
        url_label = tk.Label(qr_window, text=f'http://{ip}:{port}', font=('Consolas', 11), fg='#5D4037')
        url_label.pack(pady=5)
        
        # 提示
        hint = tk.Label(qr_window, text='或在手机浏览器中输入上方地址', font=('微软雅黑', 10), fg='#8D6E63')
        hint.pack(pady=(5, 15))
        
        # 关闭按钮
        close_btn = tk.Button(qr_window, text='关闭', font=('微软雅黑', 11), width=12,
                             command=lambda: close_qr_window(), bg='#FFB74D', fg='white')
        close_btn.pack(pady=10)
        
        qr_window.protocol('WM_DELETE_WINDOW', close_qr_window)
        qr_window.mainloop()
    except ImportError:
        logger.error('显示二维码窗口需要 tkinter 和 Pillow')
        search_status = "searching"
    except Exception as e:
        logger.error(f'显示二维码窗口失败: {e}')
        search_status = "searching"

def close_qr_window():
    """关闭 QR 窗口"""
    global qr_window
    if qr_window:
        qr_window.destroy()
        qr_window = None

def update_tray_status(status_text, icon_path=None):
    """更新托盘图标和提示"""
    global tray_icon
    if tray_icon is None:
        return
    try:
        if icon_path:
            from PIL import Image
            tray_icon.icon = Image.open(icon_path)
        tray_icon.title = f'豆包喵喵 - {status_text}'
    except:
        pass

def on_tray_show_qr(icon, item):
    """托盘菜单：显示二维码"""
    threading.Thread(target=show_qr_window, daemon=True).start()

def on_tray_show_ip(icon, item):
    """托盘菜单：显示 IP 地址"""
    ip = get_local_ip()
    port = CONFIG.get('port', 5000)
    logger.info(f'📱 手机访问: http://{ip}:{port}')

def on_tray_exit(icon, item):
    """托盘菜单：退出"""
    global tray_icon
    if tray_icon:
        tray_icon.stop()
    os._exit(0)

def create_tray_icon():
    """创建系统托盘图标"""
    global tray_icon
    try:
        import pystray
        from PIL import Image, ImageDraw, ImageFont
        
        # 创建默认图标（橙色猫咪爪印）
        img = Image.new('RGBA', (64, 64), (255, 183, 77, 255))
        draw = ImageDraw.Draw(img)
        # 画一个简单的猫爪
        draw.ellipse([16, 24, 48, 56], fill='#5D4037')  # 主掌
        draw.ellipse([12, 12, 24, 24], fill='#5D4037')  # 左上趾
        draw.ellipse([24, 8, 36, 20], fill='#5D4037')   # 中上趾
        draw.ellipse([36, 12, 48, 24], fill='#5D4037')  # 右上趾
        draw.ellipse([20, 30, 44, 52], fill='#FFE0B2')  # 掌心
        
        menu = pystray.Menu(
            pystray.MenuItem('显示二维码', on_tray_show_qr, default=True),
            pystray.MenuItem('显示 IP 地址', on_tray_show_ip),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('退出', on_tray_exit)
        )
        
        tray_icon = pystray.Icon('catdb', img, '豆包喵喵 - 搜索中...', menu)
        threading.Thread(target=tray_icon.run, daemon=True).start()
        logger.info('🐾 系统托盘已启动')
        return True
    except Exception as e:
        logger.warning(f'创建系统托盘失败: {e}')
        return False

# 搜索超时检查线程
def search_timeout_check():
    """启动后 10 秒内如果没有手机连接，则弹出二维码窗口"""
    global search_status, search_start_time
    search_start_time = time.time()
    
    while True:
        time.sleep(1)
        elapsed = time.time() - search_start_time
        
        # 有手机连接了，不需要弹窗
        if len(connected_clients) > 0:
            search_status = "connected"
            update_tray_status('已连接')
            close_qr_window()  # 如果 QR 窗口开着，关闭它
            continue
        
        # 超过 10 秒没有连接，弹出二维码
        if elapsed >= QR_TIMEOUT and search_status == "searching":
            search_status = "qr_showed"
            update_tray_status('等待扫码')
            threading.Thread(target=show_qr_window, daemon=True).start()

import os

# ============== 主入口 ==============
async def main():
    global main_loop, search_start_time
    main_loop = asyncio.get_event_loop()
    search_start_time = time.time()
    
    app = web.Application()
    app.router.add_get('/', handle_index)
    app.router.add_get('/ws', handle_websocket)
    app.router.add_get('/qr', handle_qr)
    runner = web.AppRunner(app)
    await runner.setup()
    port = CONFIG.get('port', 5000)
    await web.TCPSite(runner, '0.0.0.0', port).start()
    
    # Zeroconf 服务注册
    try:
        from zeroconf import Zeroconf, ServiceInfo
        zc = Zeroconf()
        info = ServiceInfo(
            '_catdb._tcp.local.',
            f'CatDB._catdb._tcp.local.',
            addresses=[socket.inet_aton(get_local_ip())],
            port=port,
            properties={'path': '/'},
        )
        zc.register_service(info)
        logger.info('🔍 Zeroconf 服务已注册')
    except Exception as e:
        logger.warning(f'Zeroconf 注册失败: {e}')
    
    ip = get_local_ip()
    logger.info(f'🚀 豆包喵喵服务已启动')
    logger.info(f'📱 手机访问: http://{ip}:{port}')
    logger.info(f'⏳ 等待手机连接... ({QR_TIMEOUT}秒后显示二维码)')
    
    # 启动快捷键监听
    setup_hotkey()
    
    # 启动搜索超时检查线程
    threading.Thread(target=search_timeout_check, daemon=True).start()
    
    # 启动系统托盘
    create_tray_icon()
    
    while True:
        await asyncio.sleep(3600)

if __name__ == '__main__':
    try:
        parse_args()
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info('👋 喵喵休息了')