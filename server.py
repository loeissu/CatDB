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

# 剪贴板操作锁
clipboard_lock = threading.Lock()

# ============== 配置项 ==============
CONFIG = {
    'port': 5000,
    'hotkey': 'f9',
}
# ===================================

pyautogui.PAUSE = 0
connected_clients = set()
client_configs = {}
synced_text = ""
main_loop = None
typing_in_progress = False
rebase_triggered = False  # 标记是否已触发增量模式，避免重复触发
pending_strip_punctuation = False  # 标记下次输入是否需要去除开头标点

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
            padding: 12px 14px 66px;
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
            margin-bottom: -22px; 
            position: relative; z-index: 10; padding: 0 4px;
            /* 关键修改：增加顶部间距，让猫下移，避开上面的气泡 */
            margin-top: 15px; 
        }

        .capsule-btn {
            background: var(--btn-bg); border: 2px solid #EFEBE9; color: var(--text-main);
            height: 48px; width: 100px; border-radius: 24px;
            display: flex; align-items: center; justify-content: center;
            gap: 6px; font-size: 17px; font-family: inherit;
            box-shadow: 0 4px 0 #D7CCC8; cursor: pointer;
            margin-bottom: 22px; transition: all 0.1s;
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
            padding: 0 4px 10px;
            position: relative; z-index: 1;
        }

        textarea {
            flex: 1; width: 100%; border: none; outline: none; resize: none;
            background: transparent;
            font-family: 'ZCOOL KuaiLe', cursive;
            font-size: 22px; /* 字体稍微减小以匹配密行距 */
            color: var(--text-main);
            line-height: var(--line-height);
            padding: 0 16px;
            
            /* 顶部留白大幅减小，让文字靠近猫猫 */
            padding-top: var(--header-height);
            
            background-image: 
                linear-gradient(to bottom, var(--card-bg) var(--header-height), transparent var(--header-height)),
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
            display: flex; align-items: center; gap: 8px;
            background: rgba(255, 249, 240, 0.92);
            border-top: 2px solid #EFEBE9;
            padding: 8px 10px; z-index: 500;
            backdrop-filter: blur(4px); -webkit-backdrop-filter: blur(4px);
        }
        .hotkey-scroll {
            flex: 1; min-width: 0;
            display: flex; align-items: center; gap: 8px;
            overflow-x: auto; white-space: nowrap;
            scrollbar-width: none; -ms-overflow-style: none;
        }
        .hotkey-scroll::-webkit-scrollbar { display: none; }
        .hotkey-chip {
            flex-shrink: 0;
            display: inline-flex; align-items: center; gap: 4px;
            padding: 8px 14px; border-radius: 20px;
            background: #fff; border: 2px solid #EFEBE9;
            box-shadow: 0 3px 0 #D7CCC8;
            font-family: inherit; font-size: 15px; color: var(--text-main);
            cursor: pointer; transition: all 0.1s;
        }
        .hotkey-chip:active { transform: translateY(3px); box-shadow: none; }
        .hotkey-add {
            flex-shrink: 0; width: 38px; height: 38px; border-radius: 50%;
            background: var(--accent-orange); color: #fff; border: none;
            font-size: 20px; line-height: 1; cursor: pointer;
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
        .hk-item-desc { font-size: 11px; color: var(--text-light); }
        .hk-item-btn { border: none; background: transparent; font-size: 14px; cursor: pointer; padding: 4px 6px; border-radius: 8px; color: var(--text-light); }
        .hk-item-btn.del { color: #E57373; }
        .hk-item-btn:active { background: #FBE9E7; }
        .setting-input-wide { flex: 1; min-width: 0; padding: 6px 8px; border: 2px solid #EFEBE9; border-radius: 8px; font-family: inherit; font-size: 15px; color: var(--text-main); background: #fff; }
        .hk-empty { text-align: center; font-size: 12px; color: #BCAAA4; padding: 8px 0; }
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
        <textarea 
            id="input" 
            placeholder="点击这里，告诉猫猫你想写什么..."
            autocomplete="off" autocorrect="off" autocapitalize="off" spellcheck="false"
        ></textarea>
        <div class="info-bar">
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
        let debounceTimer = null, autoClearTimer = null, enterConfirmTimer = null, autoClearCountdown = 0;

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

        input.addEventListener('keydown', (e) => {
            if(e.key === 'Enter') {
                e.preventDefault();
                if(enterConfirmTimer) clearTimeout(enterConfirmTimer);
                enterConfirmTimer = setTimeout(() => { enterConfirmTimer = null; performClear(); }, 300);
            }
        });

        // ============ 自定义快捷键模块 ============
        const DEFAULT_HOTKEYS = [
            { id: 'hk1', name: '回车', icon: '⏎', type: 'action', action: 'enter' },
            { id: 'hk2', name: 'Esc', icon: '⎋', type: 'keys', keys: 'esc' },
            { id: 'hk3', name: '切换窗口', icon: '🔄', type: 'keys', keys: 'alt+tab' },
            { id: 'hk4', name: '全选', icon: '🔲', type: 'keys', keys: 'ctrl+a' },
            { id: 'hk5', name: '删除', icon: '🗑️', type: 'keys', keys: 'delete' },
            { id: 'hk6', name: '复制', icon: '📋', type: 'keys', keys: 'ctrl+c' },
            { id: 'hk7', name: '粘贴', icon: '📌', type: 'keys', keys: 'ctrl+v' },
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

        const HOTKEYS_VERSION = '4'; // 默认快捷键列表变更时递增，用于自动覆盖旧版默认数据
        function loadHotkeys() {
            const raw = localStorage.getItem('hotkeys');
            const ver = localStorage.getItem('hotkeys_version');
            if (!raw || ver !== HOTKEYS_VERSION) {
                localStorage.setItem('hotkeys', JSON.stringify(DEFAULT_HOTKEYS));
                localStorage.setItem('hotkeys_version', HOTKEYS_VERSION);
                return DEFAULT_HOTKEYS.slice();
            }
            try { return JSON.parse(raw); } catch (e) { return DEFAULT_HOTKEYS.slice(); }
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
                row.innerHTML = `
                    <span class="hk-item-icon">${item.icon || '🔘'}</span>
                    <div class="hk-item-info">
                        <div class="hk-item-name">${item.name}</div>
                        <div class="hk-item-desc">${hkDesc(item)}</div>
                    </div>
                    <button class="hk-item-btn" data-act="edit">✏️</button>
                    <button class="hk-item-btn del" data-act="del">🗑️</button>
                `;
                row.querySelector('[data-act="edit"]').onclick = () => openHkEditor(item);
                row.querySelector('[data-act="del"]').onclick = () => {
                    list.splice(idx, 1);
                    saveHotkeys(list);
                    renderHotkeys();
                };
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

        connect();
        window.onload = () => setTimeout(() => input.focus(), 100);
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
    common = 0
    for i in range(min(len(old), len(new))):
        if old[i] == new[i]: common += 1
        else: break
    return len(old) - common, new[common:]

def type_text(text):
    global typing_in_progress
    if not text: return
    typing_in_progress = True
    try:
        with clipboard_lock:
            try: orig = pyperclip.paste()
            except: orig = ''
            pyperclip.copy(text)
            if platform.system() == 'Darwin': pyautogui.hotkey('command', 'v')
            else: pyautogui.hotkey('ctrl', 'v')
            time.sleep(0.1)
            try: pyperclip.copy(orig)
            except: pass
    finally: typing_in_progress = False

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
            if len(parts) == 1:
                pyautogui.press(parts[0])
            else:
                pyautogui.hotkey(*parts)
        elif stype == 'action':
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

def send_backspaces(count):
    global typing_in_progress
    if count <= 0: return
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
                    if add_txt: type_text(add_txt); print(f'⌨️ {add_txt}')
                    synced_text = new_txt
                elif data.get('type') == 'reset':
                    synced_text = ""
                    pending_strip_punctuation = True  # 清空后下次输入需要检查标点
                    print('🔄 重置')
                elif data.get('type') == 'shortcut':
                    # 手机端自定义快捷键：按键组合 / 内置动作 / 启动脚本
                    ok = execute_shortcut(data.get('sc') or {})
                    await ws.send_json({'type': 'shortcut_result', 'ok': ok})
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

async def main():
    global main_loop
    main_loop = asyncio.get_event_loop()
    app = web.Application()
    app.router.add_get('/', handle_index)
    app.router.add_get('/ws', handle_websocket)
    runner = web.AppRunner(app)
    await runner.setup()
    port = CONFIG.get('port', 5000)
    await web.TCPSite(runner, '0.0.0.0', port).start()
    
    print('='*50 + f'\n🚀 豆包喵喵服务已启动\n📱 手机访问: http://{get_local_ip()}:{port}\n' + '='*50)
    setup_hotkey()
    while True: await asyncio.sleep(3600)

if __name__ == '__main__':
    try: asyncio.run(main())
    except KeyboardInterrupt: print('\n👋 喵喵休息了')