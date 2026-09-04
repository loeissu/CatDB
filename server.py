#!/usr/bin/env python3
"""
手机语音输入 → 电脑实时上屏（豆包喵喵·精调修正版）
UI变更：精致胡须、紧凑行距、猫咪下移、字体沉底
"""

import time as _clock
_APP_START_TS = _clock.time()  # 置于所有 import 之前：统计模块导入耗时（启动优化用）

import asyncio
import socket
import json
import platform
import sys
import threading
import time
import logging
import argparse
import queue
import os
import signal
import webbrowser
from aiohttp import web
import aiohttp


# ---- pyautogui 懒加载：其依赖链（pyscreeze→cv2→numpy/PIL）较重，
#      冷启动时可省约 0.3-1s，只在首次模拟键鼠操作时才真正 import ----
class _LazyModule:
    def __init__(self, name, after_load=None):
        object.__setattr__(self, '_name', name)
        object.__setattr__(self, '_after', after_load)
        object.__setattr__(self, '_mod', None)

    def _load(self):
        mod = object.__getattribute__(self, '_mod')
        if mod is None:
            import importlib
            mod = importlib.import_module(object.__getattribute__(self, '_name'))
            after = object.__getattribute__(self, '_after')
            if after is not None:
                after(mod)
            object.__setattr__(self, '_mod', mod)
        return mod

    def __getattr__(self, key):
        return getattr(self._load(), key)

    def __setattr__(self, key, value):
        setattr(self._load(), key, value)


def _pyautogui_init(mod):
    mod.PAUSE = 0
    mod.FAILSAFE = False  # 远程触控板控制场景，禁用左上角安全保护（否则移动到角落会抛异常）


pyautogui = _LazyModule('pyautogui', _pyautogui_init)
import pyperclip
import subprocess

try:
    import webview  # 桌面 GUI 依赖；未安装时仍可 --minimized/纯后端运行
except ImportError:
    webview = None

__version__ = "2.2.13"

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

# ============== 全局状态 & 同步原语 ==============
connected_clients = set()
client_configs = {}
_clients_lock = threading.Lock()  # 保护 connected_clients / client_configs

def get_clients_snapshot():
    """线程安全地获取客户端快照"""
    with _clients_lock:
        return list(connected_clients), dict(client_configs)

def add_client(ws):
    with _clients_lock:
        connected_clients.add(ws)

def remove_client(ws):
    with _clients_lock:
        connected_clients.discard(ws)
        client_configs.pop(ws, None)

def set_client_config(ws, config):
    with _clients_lock:
        client_configs[ws] = config

def get_detect_keyboard_enabled():
    with _clients_lock:
        return any(c.get('detect_keyboard') for c in client_configs.values())

synced_text = ""
# 手机端实时输入预览：最新文本 + 时间戳（桌面 GUI 轮询展示，随时间过期自动消失）
live_typing_text = ""
live_typing_ts = 0.0
_live_entry = None       # 当前输入会话对应的运行日志条目（LOG_BUFFER 内的 dict 引用）
_live_start_ts = 0.0     # 当前输入会话开始时间
main_loop = None
typing_in_progress = False
rebase_triggered = False  # 标记是否已触发增量模式，避免重复触发
pending_strip_punctuation = False  # 标记下次输入是否需要去除开头标点

# 系统托盘/桌面窗口相关
zeroconf_instance = None  # 保持 Zeroconf 引用，防止 GC 导致服务注销

# 切换窗口（Alt+Tab 连续切换）状态：按住 Alt 保持 1 秒，期间再次触发只按 Tab
hotkey_alt_held = False
hotkey_alt_timer = None
hotkey_alt_lock = threading.Lock()

# 触控板模式开关（默认开；GUI 开关会持久化到配置）
touchpad_enabled = True

# pynput 监听器句柄（快捷键/鼠标）。热键变更时先停旧的再重建，避免重复监听
HOTKEY_LISTENERS = []

# ============== 配置项 ==============
CONFIG = {
    'port': 5000,
    'hotkey': 'f9',
}
# ===================================

def parse_args():
    parser = argparse.ArgumentParser(description='豆包喵喵 - 手机语音输入 → 电脑实时上屏')
    parser.add_argument('--port', type=int, default=5000, help='初始端口 (默认: 5000)')
    parser.add_argument('--hotkey', type=str, default=None, help='清空快捷键 (默认: f9，可由配置文件覆盖)')
    parser.add_argument('--max-port-attempts', type=int, default=20, help='最大端口尝试次数 (默认: 20)')
    parser.add_argument('--minimized', action='store_true', help='最小化启动（开机自启模式，不显示窗口）')
    args = parser.parse_args()
    CONFIG['port'] = args.port
    if args.hotkey:
        CONFIG['hotkey'] = args.hotkey.strip().lower()
    CONFIG['max_port_attempts'] = args.max_port_attempts
    CONFIG['minimized'] = args.minimized

def load_persisted_prefs():
    """启动时套用持久化偏好（热键 / 触控板开关）"""
    global touchpad_enabled
    cfg = load_catdb_config()
    if not CONFIG.get('hotkey') and cfg.get('hotkey'):
        CONFIG['hotkey'] = str(cfg['hotkey']).strip().lower()
    if 'touchpad_enabled' in cfg:
        touchpad_enabled = bool(cfg['touchpad_enabled'])
    CONFIG['hotkey'] = CONFIG.get('hotkey') or 'f9'

# ============== 端口自动探测 ==============
def check_port_available(host, port):
    """
    使用原生 socket 检测端口是否可用。
    返回 True 表示端口空闲，False 表示已被占用。
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.settimeout(0.1)  # 100ms 超时，快速检测
            s.bind((host, port))
            return True
    except OSError:
        return False

def find_available_port(start_port, host='0.0.0.0', max_attempts=20):
    """
    从 start_port 开始，依次向下探测可用端口。
    返回第一个可用端口号；若全部占满则返回 None。
    """
    for offset in range(max_attempts):
        candidate = start_port + offset
        if check_port_available(host, candidate):
            return candidate
    return None

def get_local_ip():
    """
    获取本机局域网 IP。
    优先使用 netifaces 遍历网卡，失败则回退到 socket 连接外网法，最终兜底 127.0.0.1。
    """
    # 1. 优先使用 netifaces 遍历网卡（最可靠，无需外网）。
    #    先找局域网私网地址（192.168./10./172.16-31.），避免 VPN/虚拟网卡抢在前面
    def _is_private(ip):
        try:
            parts = ip.split('.')
            if len(parts) != 4:
                return False
            a, b = int(parts[0]), int(parts[1])
            return a == 10 or a == 192 or (a == 172 and 16 <= b <= 31)
        except Exception:
            return False
    try:
        import netifaces
        candidates = []
        for iface in netifaces.interfaces():
            addrs = netifaces.ifaddresses(iface).get(netifaces.AF_INET, [])
            for addr in addrs:
                ip = addr.get('addr', '')
                if ip and not ip.startswith('127.'):
                    candidates.append(ip)
        for ip in candidates:
            if _is_private(ip):
                return ip
        if candidates:
            return candidates[0]
    except Exception:
        pass
    # 2. 回退：socket.gethostbyname_ex
    try:
        hostname = socket.gethostname()
        ips = socket.gethostbyname_ex(hostname)[2]
        for ip in ips:
            if ip.startswith('192.168.') or ip.startswith('10.'):
                return ip
        for ip in ips:
            if ip.startswith('172.') and 16 <= int(ip.split('.')[1]) <= 31:
                return ip
    except Exception:
        pass
    # 3. 最后兜底：尝试连接外网（需要联网），失败则返回 127.0.0.1
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'

def compute_diff(old, new):
    """
    计算两个字符串的差异：返回 (需要删除的字符数, 需要添加的文本)。
    支持中间编辑场景：通过前后缀匹配定位变更区域。
    """
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
    max_suffix = min(len(old_tail), len(new_tail))
    for i in range(max_suffix):
        if old_tail[-(i+1)] == new_tail[-(i+1)]:
            suffix += 1
        else:
            break
    # 边界保护：防止 prefix + suffix 超过字符串长度
    suffix = min(suffix, len(old) - prefix, len(new) - prefix)
    # 需要删除的字符数 = 旧文本中除去前后缀的部分
    del_count = len(old) - prefix - suffix
    # 需要添加的文本 = 新文本中除去前后缀的部分
    add_text = new[prefix:len(new)-suffix] if suffix > 0 else new[prefix:]
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

# 安全：仅允许白名单内的命令（防止任意代码执行）
ALLOWED_COMMANDS = {
    'notepad': ['notepad.exe'],
    'calc': ['calc.exe'],
    'explorer': ['explorer.exe'],
    'cmd': ['cmd.exe'],
    'powershell': ['powershell.exe'],
}

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
            # 安全：仅允许白名单命令，禁止 shell=True
            cmd_name = sc.get('cmd', '').strip().lower()
            if not cmd_name:
                return False
            if cmd_name not in ALLOWED_COMMANDS:
                logger.warning(f'拒绝执行非白名单命令: {cmd_name}')
                return False
            try:
                subprocess.Popen(ALLOWED_COMMANDS[cmd_name], shell=False)
            except Exception as e:
                logger.error(f'启动命令失败: {e}')
                return False
        else:
            return False
        # 按键类操作属于“电脑介入”，触发增量模式，避免与手机端输入冲突
        if get_detect_keyboard_enabled():
            reset_synced_text()
        return True
    except Exception as e:
        logger.warning(f'⚠️ 快捷键执行失败: {e}')
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
        logger.warning(f'⚠️ 触控执行失败: {e}')
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

# ============== 手机图片 → 电脑剪贴板并粘贴到光标处 ==============
def _set_image_clipboard(img):
    """把 PIL 图片写入 Windows 剪贴板（CF_DIB）"""
    import ctypes
    import struct
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    CF_DIB = 8
    GMEM_MOVEABLE = 0x0002
    GMEM_ZEROINIT = 0x0040

    # 必须显式声明指针/句柄签名，否则 64 位下 GlobalLock 返回的指针会被截断成 0 → 崩溃
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    user32.CloseClipboard.restype = wintypes.BOOL
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.restype = wintypes.BOOL
    kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalFree.restype = wintypes.HGLOBAL

    img = img.convert('RGBA')
    w, h = img.size
    # 转 BGRA 自下而上（bottom-up DIB），兼容绝大多数粘贴目标。
    # 用单块 bytearray 逐行累积，避免 rows 列表+join 产生两份全图拷贝，降低大图峰值内存
    raw = bytearray(w * h * 4)
    off = 0
    for y in range(h - 1, -1, -1):
        row = img.crop((0, y, w, y + 1)).tobytes('raw', 'BGRA')
        raw[off:off + len(row)] = row
        off += len(row)
    header = struct.pack('<LiiHHIIiiII', 40, w, h, 1, 32, 0, len(raw), 0, 0, 0, 0)
    size = len(header) + len(raw)

    if not user32.OpenClipboard(None):
        raise OSError('OpenClipboard 失败')
    try:
        user32.EmptyClipboard()
        h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE | GMEM_ZEROINIT, size)
        if not h_mem:
            raise OSError('GlobalAlloc 失败')
        ptr = kernel32.GlobalLock(h_mem)
        try:
            ctypes.memmove(ptr, header, len(header))
            ctypes.memmove(ptr + len(header), raw, len(raw))
        finally:
            kernel32.GlobalUnlock(h_mem)
        if not user32.SetClipboardData(CF_DIB, h_mem):
            # 失败时释放内存，避免泄漏
            kernel32.GlobalFree(h_mem)
            raise OSError('SetClipboardData 失败')
        # 成功后内存归剪贴板所有，不再释放
    finally:
        user32.CloseClipboard()

def paste_image_to_computer(image_bytes, do_paste=True):
    """把手机发来的图片放进剪贴板，并 Ctrl+V 粘贴到电脑当前光标处"""
    global typing_in_progress
    if not image_bytes:
        return False, '空数据'
    try:
        from io import BytesIO
        from PIL import Image
        img = Image.open(BytesIO(image_bytes))
        img.load()
        if img.width > 4096 or img.height > 4096:
            img.thumbnail((4096, 4096), Image.LANCZOS)
        _set_image_clipboard(img)
        if do_paste and platform.system() == 'Windows':
            typing_in_progress = True
            try:
                pyautogui.hotkey('ctrl', 'v')
                time.sleep(0.05)
            finally:
                typing_in_progress = False
        logger.info('🖼️ 已接收手机图片 %dx%d → 剪贴板' % (img.width, img.height))
        return True, '%dx%d' % (img.width, img.height)
    except Exception as e:
        logger.error('接收图片失败: %s', e)
        return False, str(e)

def _resource_path(rel):
    """返回打包后(sys._MEIPASS)或源码目录下的资源绝对路径"""
    if hasattr(sys, '_MEIPASS'):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, rel)

async def handle_index(req):
    """手机页面：唯一事实来源为 www/index.html（源码 / PyInstaller datas 打包同一份）"""
    try:
        p = _resource_path(os.path.join('www', 'index.html'))
        with open(p, 'r', encoding='utf-8') as f:
            html = f.read()
        return web.Response(text=html, content_type='text/html', headers={'Cache-Control': 'no-store'})
    except Exception as e:
        logger.error('读取 www/index.html 失败: %s', e)
        return web.Response(
            text='<meta charset="utf-8"><h3 style="font-family:sans-serif">豆包喵喵资源缺失</h3>'
                 '<p style="font-family:sans-serif">未找到 www/index.html，请检查安装是否完整。</p>',
            content_type='text/html', status=500)
async def handle_websocket(req):
    global synced_text, touchpad_enabled
    # heartbeat=30：服务端每 30s 发一次 ping 帧，收不到 pong 即判定死连接并关闭，
    # 防止手机静默断线（杀进程/切网/休眠）后 ws 对象与任务长期滞留内存
    ws = web.WebSocketResponse(heartbeat=30)
    await ws.prepare(req)
    add_client(ws)
    logger.info('📱 手机已连接')
    try:
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                data = json.loads(msg.data)
                if data.get('type') == 'config':
                    set_client_config(ws, {'detect_keyboard': data.get('detectKeyboard')})
                elif data.get('type') == 'ping':
                    # 客户端保活心跳：回复 pong，让手机端及时感知链路已死并重连
                    try:
                        await ws.send_json({'type': 'pong'})
                    except Exception:
                        pass
                elif data.get('type') == 'diff':
                    global rebase_triggered, pending_strip_punctuation
                    new_txt = data.get('newText', '')
                    d_cnt, add_txt = compute_diff(synced_text, new_txt)
                    # 触发增量/清空后，下一次无回退的输入才剪除句首标点
                    if pending_strip_punctuation and d_cnt == 0 and add_txt:
                        # 中英文常见标点符号（不含书名号、方括号等成对符号，但保留引号）
                        punctuations = "，。、；：？！\"\"''·…—～,.;:?!'\""
                        if add_txt[0] in punctuations:
                            add_txt = add_txt[1:]  # 只剪除发送内容的标点
                            logger.debug('✂️ 去除开头标点')
                        pending_strip_punctuation = False  # 只处理一次
                    rebase_triggered = False  # 手机端有新输入，重置增量触发标志
                    if d_cnt: 
                        send_backspaces(d_cnt)
                        logger.debug(f'⌫ {d_cnt}')
                    if add_txt: 
                        type_text(add_txt)
                        logger.debug(f'⌨️ {add_txt!r}')
                    synced_text = new_txt
                    update_live_typing(new_txt)
                elif data.get('type') == 'reset':
                    synced_text = ""
                    pending_strip_punctuation = True  # 清空后下次输入需要检查标点
                    clear_live_typing()
                    logger.info('🔄 重置')
                elif data.get('type') == 'shortcut':
                    # 手机端自定义快捷键：按键组合 / 内置动作 / 启动脚本
                    ok = execute_shortcut(data.get('sc') or {})
                    await ws.send_json({'type': 'shortcut_result', 'ok': ok})
                elif data.get('type') == 'touch':
                    # 手机端触控板：移动 / 点击 / 双击 / 右键 / 滚动
                    # 尊重桌面 GUI 的“触控板模式”开关：关闭时忽略手机触控指令
                    if not touchpad_enabled:
                        logger.info('触控板模式已关闭，忽略手机触控指令')
                    else:
                        handle_touch(data)
                elif data.get('type') == 'touchpad_toggle':
                    # 触控板模式开关
                    new_state = data.get('enabled', True)
                    touchpad_enabled = new_state
                    status = '开启' if new_state else '关闭'
                    logger.info(f'触控板模式: {status}')
                elif data.get('type') == 'image':
                    # 手机图片：解码 → 剪贴板 → 粘贴到电脑当前光标处
                    import base64
                    payload = data.get('data') or data.get('b64') or ''
                    if payload.startswith('data:') and ',' in payload:
                        payload = payload.split(',', 1)[1]
                    try:
                        raw = base64.b64decode(payload)
                    except Exception:
                        raw = b''
                    loop = asyncio.get_event_loop()
                    ok, info = await loop.run_in_executor(None, paste_image_to_computer, raw)
                    try:
                        await ws.send_json({'type': 'image_result', 'ok': ok, 'info': str(info)})
                    except Exception:
                        pass
    finally:
        remove_client(ws)
        logger.info('📱 断开')
    return ws

async def broadcast_clear_with_blur():
    for ws in list(connected_clients):
        try: await ws.send_json({'type': 'clear_with_blur'})
        except: pass

async def broadcast_rebase():
    for ws in get_clients_snapshot()[0]:
        try: await ws.send_json({'type': 'rebase'})
        except: pass

def update_live_typing(txt):
    """手机端输入实时预览 + 写入运行日志：
    - 新会话开始时在日志中落一条「正在输入」（记录开始时间）
    - 会话期间实时更新该条内容（日志内刷新，不额外弹徽标）
    - 结束（clear_live_typing）时固化为「输入完成 起→止：内容」，关闭客户端才消失"""
    global live_typing_text, live_typing_ts, _live_entry, _live_start_ts
    txt = txt or ''
    now = time.time()
    if txt and _live_entry is None:
        # 新输入会话：写入日志（带开始时间戳）
        _live_start_ts = now
        entry = {'time': time.strftime('%H:%M:%S'), 'level': 'info',
                 'msg': f'📱 正在输入：{txt}', '_live': True, '_start_ts': now}
        with LOG_BUFFER_LOCK:
            LOG_BUFFER.append(entry)
        _live_entry = entry
    elif txt and _live_entry is not None:
        # 会话中：实时更新该条日志的内容（保留开始时间）
        _live_entry['msg'] = f'📱 正在输入：{txt}'
    live_typing_text = txt
    live_typing_ts = now


def clear_live_typing():
    """结束当前输入会话：把日志中的「正在输入」固化为含起止时间与内容的完成记录"""
    global live_typing_text, live_typing_ts, _live_entry, _live_start_ts
    entry = _live_entry
    if entry is not None:
        start = time.strftime('%H:%M:%S', time.localtime(entry.get('_start_ts') or time.time()))
        end = time.strftime('%H:%M:%S')
        dur = ''
        s = entry.get('_start_ts')
        if s:
            dur = f'（{max(0, int(time.time() - s))}s）'
        txt = live_typing_text
        with LOG_BUFFER_LOCK:
            if entry in LOG_BUFFER:  # 若已被 400 条环形缓冲挤出则跳过
                if txt:
                    entry['msg'] = f'📱 输入完成 {start}→{end}{dur}：{txt}'
                else:
                    entry['msg'] = f'📱 输入完成 {start}→{end}{dur}'
                entry.pop('_live', None)
                entry.pop('_start_ts', None)
    _live_entry = None
    _live_start_ts = 0.0
    live_typing_text = ''
    live_typing_ts = 0.0

def reset_synced_text():
    global synced_text, rebase_triggered, pending_strip_punctuation
    if typing_in_progress: return
    if rebase_triggered: return  # 已触发过增量模式，等待手机端新输入后再允许触发
    if synced_text:
        synced_text = ""
        rebase_triggered = True  # 标记已触发
        pending_strip_punctuation = True  # 下次输入需要检查标点
        clear_live_typing()
        logger.info('🔄 电脑端输入，触发增量同步')
        if main_loop: asyncio.run_coroutine_threadsafe(broadcast_rebase(), main_loop)

def setup_hotkey():
    """启动（或重建）键盘/鼠标监听。旧监听器先停止，支持运行中更换热键"""
    global main_loop
    for l in list(HOTKEY_LISTENERS):
        try:
            l.stop()
        except Exception:
            pass
    HOTKEY_LISTENERS.clear()
    hotkey = CONFIG.get('hotkey', 'f9').strip().lower()
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
                if k.lower() not in IGNORED and get_detect_keyboard_enabled():
                    reset_synced_text()
            except: pass

        # 鼠标监听 - 左键点击触发增量模式
        def on_click(x, y, button, pressed):
            try:
                # 只在左键按下时触发，释放时不触发
                if button == mouse.Button.left and pressed:
                    if get_detect_keyboard_enabled():
                        reset_synced_text()
            except: pass

        kb = keyboard.Listener(on_press=on_press)
        ms = mouse.Listener(on_click=on_click)
        kb.start()
        ms.start()
        HOTKEY_LISTENERS.extend([kb, ms])
        if hotkey: logger.info('🎹 热键: [%s]', hotkey)
        logger.info('🖱️ 鼠标左键监测已启用')
    except Exception as e:
        logger.warning('⚠️  热键需安装 pynput: %s', e)

async def handle_qr(req):
    try:
        import qrcode
        from io import BytesIO
        # 支持 /qr?ip=192.168.x.x 指定二维码指向的 IP（桌面 GUI 选择 IP 后刷新）
        ip = (req.query.get('ip') or '').strip() or get_local_ip()
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

async def handle_desktop(req):
    """桌面 GUI 页面： serving www/desktop.html，供 pywebview 主窗口加载"""
    try:
        base = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(base, 'www', 'desktop.html')
        # PyInstaller 单文件打包后资源在 sys._MEIPASS
        if not os.path.exists(path) and hasattr(sys, '_MEIPASS'):
            path = os.path.join(sys._MEIPASS, 'www', 'desktop.html')
        with open(path, 'r', encoding='utf-8') as f:
            html = f.read()
        return web.Response(text=html, content_type='text/html', headers={'Cache-Control': 'no-store'})
    except Exception as e:
        return web.Response(text=f'desktop.html load failed: {e}', status=500)


async def handle_vendor_asset(req):
    """www/vendor/*（Capacitor 运行时/插件代理），浏览器访问手机页时可正常加载"""
    name = (req.match_info.get('name') or '')
    if not name or '/' in name or '\\' in name or '..' in name:
        return web.Response(status=404)
    try:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'www', 'vendor', name)
        if not os.path.exists(path) and hasattr(sys, '_MEIPASS'):
            path = os.path.join(sys._MEIPASS, 'www', 'vendor', name)
        if not os.path.isfile(path):
            return web.Response(status=404)
        with open(path, 'rb') as f:
            data = f.read()
        ctype = 'application/javascript' if name.endswith('.js') else 'application/octet-stream'
        return web.Response(body=data, content_type=ctype, headers={'Cache-Control': 'no-cache'})
    except Exception:
        return web.Response(status=404)


async def handle_manifest(req):
    """www/manifest.json：手机页声明了 <link rel="manifest">，浏览器访问时能取到（避免 404）"""
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(base, 'www', 'manifest.json')
    if not os.path.isfile(path):
        return web.Response(status=404)
    with open(path, 'rb') as f:
        data = f.read()
    return web.Response(body=data, content_type='application/manifest+json', headers={'Cache-Control': 'no-cache'})

# ============== 日志回环缓冲（供桌面 GUI 日志面板） ==============
import collections
LOG_BUFFER = collections.deque(maxlen=400)
LOG_BUFFER_LOCK = threading.Lock()

class _RingBufferHandler(logging.Handler):
    """把 INFO/WARN/ERROR 写入内存环，GUI 通过 API 轮询读取"""
    def emit(self, record):
        try:
            msg = self.format(record)
            lvl = record.levelname
            if lvl not in ('INFO', 'WARNING', 'ERROR', 'DEBUG'):
                lvl = 'INFO'
            tag = {'INFO': 'info', 'WARNING': 'warn', 'ERROR': 'error', 'DEBUG': 'info'}.get(lvl, 'info')
            with LOG_BUFFER_LOCK:
                LOG_BUFFER.append({'time': time.strftime('%H:%M:%S'), 'level': tag, 'msg': msg})
        except Exception:
            pass

def _install_ring_handler():
    h = _RingBufferHandler()
    h.setFormatter(logging.Formatter('%(message)s'))
    h.setLevel(logging.INFO)
    logger.addHandler(h)
    return h

_ring_handler = _install_ring_handler()

# ============== 共享辅助（WebviewAPI 与 HTTP JSON API 共用） ==============
def read_log_buffer():
    with LOG_BUFFER_LOCK:
        return list(LOG_BUFFER)

def clear_log_buffer():
    with LOG_BUFFER_LOCK:
        LOG_BUFFER.clear()

def _is_private_ip(ip):
    """是否局域网私网地址（192.168.* / 10.* / 172.16-31.*），用于排序优选"""
    try:
        parts = ip.split('.')
        if len(parts) != 4:
            return False
        a, b = int(parts[0]), int(parts[1])
        return a == 10 or a == 192 or (a == 172 and 16 <= b <= 31)
    except Exception:
        return False

def list_ips():
    ips = []
    try:
        import netifaces
        for iface in netifaces.interfaces():
            for addr in netifaces.ifaddresses(iface).get(netifaces.AF_INET, []):
                ip = addr.get('addr', '')
                if ip and not ip.startswith('127.'):
                    ips.append(ip)
    except Exception:
        try:
            hostname = socket.gethostname()
            ips = [ip for ip in socket.gethostbyname_ex(hostname)[2] if not ip.startswith('127.')]
        except Exception:
            ips = []
    # 去重 + 私网地址排前（避免 VPN/虚拟网卡抢在前面导致手机连不上）
    seen = set()
    dedup = [ip for ip in ips if not (ip in seen or seen.add(ip))]
    dedup.sort(key=lambda ip: (0 if _is_private_ip(ip) else 1, ip))
    if not dedup:
        dedup = ['127.0.0.1']
    return dedup

def catdb_config_dir():
    """配置持久化目录：%APPDATA%/CatDB（Windows），否则仓库目录"""
    try:
        if platform.system() == 'Windows':
            base = os.environ.get('APPDATA') or os.path.expanduser('~')
            d = os.path.join(base, 'CatDB')
        else:
            d = os.path.dirname(os.path.abspath(__file__))
        os.makedirs(d, exist_ok=True)
        return d
    except Exception:
        return os.path.dirname(os.path.abspath(__file__))

def load_catdb_config():
    try:
        with open(os.path.join(catdb_config_dir(), 'config.json'), 'r', encoding='utf-8') as f:
            cfg = json.load(f)
            return cfg if isinstance(cfg, dict) else {}
    except Exception:
        return {}

def save_catdb_config(cfg):
    try:
        path = os.path.join(catdb_config_dir(), 'config.json')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error('保存配置失败: %s', e)
        return False

def registry_set_autostart(enable):
    """Windows 开机自启（HKCU Run）。非 Windows 直接忽略"""
    if platform.system() != 'Windows':
        return
    import winreg
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
    try:
        if enable:
            winreg.SetValueEx(key, "CatDB", 0, winreg.REG_SZ, autostart_command())
        else:
            try:
                winreg.DeleteValue(key, "CatDB")
            except FileNotFoundError:
                pass
    finally:
        winreg.CloseKey(key)

def autostart_command():
    """自启动命令行：打包后为 exe --minimized；源码运行为 python server.py --minimized"""
    if getattr(sys, 'frozen', False):
        return f'"{sys.executable}" --minimized'
    py = sys.executable
    script = os.path.abspath(__file__)
    return f'"{py}" "{script}" --minimized'

_FILE_HANDLER = None

def init_file_logging():
    """把日志同时写入 %APPDATA%/CatDB/catdb.log，保证无控制台时也能排查问题"""
    global _FILE_HANDLER
    if _FILE_HANDLER is not None:
        return
    try:
        path = os.path.join(catdb_config_dir(), 'catdb.log')
        h = logging.FileHandler(path, encoding='utf-8')
        h.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
        h.setLevel(logging.INFO)
        logger.addHandler(h)
        _FILE_HANDLER = h
    except Exception:
        pass

def build_status_payload():
    """桌面 GUI / 浏览器共用的状态负载"""
    return {
        'success': True,
        'running': service_is_running(),
        'port': CONFIG.get('port', 5000),
        'ip': get_local_ip(),
        'ips': list_ips(),
        'touchpad_enabled': bool(touchpad_enabled),
        'hotkey': CONFIG.get('hotkey', 'f9'),
        'auto_start': bool(load_catdb_config().get('auto_start', False)),
        'service_name': 'CatDB (_catdb._tcp.local.)',
        'version': __version__,
        'live_typing': live_typing_text,
        'live_typing_ts': live_typing_ts,
    }

# ============== HTTP JSON API（浏览器模式 / 调试用，pywebview 走 window.pywebview.api） ==============
CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Cache-Control': 'no-store',
}

def _json(data, status=200):
    return web.json_response(data, status=status, headers=CORS_HEADERS)

async def handle_api_status(req):
    return _json(build_status_payload())

async def handle_api_logs(req):
    return _json({'success': True, 'logs': read_log_buffer()})

async def handle_api_cors(req):
    return web.Response(status=204, headers=CORS_HEADERS)

async def handle_api_action(req):
    """统一动作入口：{action: start|stop|touchpad|autostart|hotkey|clear_logs, ...}"""
    try:
        body = await req.json()
    except Exception:
        return _json({'success': False, 'error': 'invalid json'}, 400)
    action = body.get('action')
    if action == 'start':
        ok, port = start_service_now()
        return _json({'success': ok, **build_status_payload()})
    if action == 'stop':
        stop_service_now()
        return _json({'success': True, **build_status_payload()})
    if action == 'touchpad':
        global touchpad_enabled
        touchpad_enabled = bool(body.get('enabled', True))
        cfg = load_catdb_config(); cfg['touchpad_enabled'] = touchpad_enabled; save_catdb_config(cfg)
        logger.info('触控板模式: %s', '开启' if touchpad_enabled else '关闭')
        return _json({'success': True, 'touchpad_enabled': touchpad_enabled})
    if action == 'autostart':
        enabled = bool(body.get('enabled', False))
        cfg = load_catdb_config(); cfg['auto_start'] = enabled; save_catdb_config(cfg)
        registry_set_autostart(enabled)
        logger.info('开机自启：%s', '开启' if enabled else '关闭')
        return _json({'success': True, 'enabled': enabled})
    if action == 'hotkey':
        hk = str(body.get('hotkey', '')).strip().lower()
        if not hk:
            return _json({'success': False, 'error': 'hotkey empty'}, 400)
        CONFIG['hotkey'] = hk
        cfg = load_catdb_config(); cfg['hotkey'] = hk; save_catdb_config(cfg)
        if service_is_running():
            setup_hotkey()  # 运行中立即重建监听；未运行时下次启动自动生效
        logger.info('清屏快捷键已设置为: [%s]', hk)
        return _json({'success': True, 'hotkey': hk})
    if action == 'clear_logs':
        clear_log_buffer()
        return _json({'success': True})
    return _json({'success': False, 'error': f'unknown action: {action}'}, 400)

# ============== 服务生命周期（可启动/停止的 aiohttp 服务） ==============
service_state = {
    'thread': None,
    'loop': None,
    'ready': threading.Event(),
    'stop_event': None,  # asyncio.Event，由服务线程内的协程创建
    'runner': None,
    'running': False,
}

def service_is_running():
    return bool(service_state['running'])

def _start_service_inner():
    """在子线程里运行 asyncio 服务循环；绑定实际端口后置 ready"""
    async def _serve():
        global main_loop, zeroconf_instance
        main_loop = asyncio.get_event_loop()
        # 端口自动探测
        desired_port = CONFIG.get('port', 5000)
        max_attempts = CONFIG.get('max_port_attempts', 20)
        actual_port = find_available_port(desired_port, max_attempts=max_attempts)
        if actual_port is None:
            logger.error('❌ 无法找到可用端口：从 %d 起的 %d 个端口均被占用', desired_port, max_attempts)
            service_state['running'] = False
            service_state['ready'].set()
            return
        if actual_port != desired_port:
            logger.warning('原始端口 %d 被占用，已自动切换至可用端口: %d', desired_port, actual_port)
        CONFIG['port'] = actual_port

        app = web.Application()
        app.router.add_get('/', handle_index)
        app.router.add_get('/ws', handle_websocket)
        app.router.add_get('/qr', handle_qr)
        app.router.add_get('/desktop.html', handle_desktop)
        app.router.add_get('/vendor/{name:.*}', handle_vendor_asset)
        app.router.add_get('/manifest.json', handle_manifest)
        # JSON API（浏览器模式的桌面 GUI 使用；pywebview 模式走 window.pywebview.api）
        app.router.add_get('/api/status', handle_api_status)
        app.router.add_get('/api/logs', handle_api_logs)
        app.router.add_post('/api/action', handle_api_action)
        app.router.add_options('/api/action', handle_api_cors)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', actual_port)
        await site.start()
        service_state['runner'] = runner
        service_state['running'] = True

        # Zeroconf（异步 API：Windows 默认 ProactorEventLoop 下，同步 Zeroconf() 会抛 EventLoopBlocked，
        # 导致注册一直失败；AsyncZeroconf 兼容 Proactor 循环）
        try:
            from zeroconf.asyncio import AsyncZeroconf, AsyncServiceInfo
            zeroconf_instance = AsyncZeroconf()
            info = AsyncServiceInfo(
                '_catdb._tcp.local.',
                f'CatDB._catdb._tcp.local.',
                addresses=[socket.inet_aton(get_local_ip())],
                port=actual_port,
                properties={'path': '/'},
            )
            # 撞名时自动改名重试（CatDB → CatDB-2…），避免与其他实例/残留广播冲突直接失败
            await zeroconf_instance.async_register_service(info, allow_name_change=True)
            logger.info('🔍 Zeroconf 服务已注册')
        except Exception as e:
            logger.warning('Zeroconf 注册失败（不影响使用）: %s: %s', type(e).__name__, e)

        setup_hotkey()

        ip = get_local_ip()
        logger.info('=' * 50)
        logger.info('🚀 豆包喵喵服务已启动')
        logger.info('   本机访问：http://127.0.0.1:%d', actual_port)
        logger.info('   局域网设备访问：http://%s:%d', ip, actual_port)
        logger.info('=' * 50)
        # 停止信号：用 asyncio.Event，绝不阻塞事件循环
        # （实测：协程里做 threading.Event.wait() 会饿死 Windows Proactor 循环，HTTP 全部超时）
        stop_ev = asyncio.Event()
        service_state['stop_event'] = stop_ev
        service_state['ready'].set()
        await stop_ev.wait()

        logger.info('正在关闭服务...')
        service_state['running'] = False
        if zeroconf_instance:
            try:
                await zeroconf_instance.async_unregister_all_services()
                await zeroconf_instance.async_close()
            except Exception:
                pass
            zeroconf_instance = None
        try:
            await runner.cleanup()
        except Exception:
            pass
        # 停止全局热键/鼠标监听（重启服务时会在 setup_hotkey 中重建）
        for l in list(HOTKEY_LISTENERS):
            try:
                l.stop()
            except Exception:
                pass
        HOTKEY_LISTENERS.clear()
        logger.info('👋 服务已停止')

    service_state['loop'] = asyncio.new_event_loop()
    asyncio.set_event_loop(service_state['loop'])
    try:
        service_state['loop'].run_until_complete(_serve())
    except Exception:
        logger.exception('❌ 服务线程异常退出')
        service_state['running'] = False
        service_state['ready'].set()  # 让等待方立即返回，而不是干等 15s
    finally:
        try:
            service_state['loop'].close()
        except Exception:
            pass

def start_service_now():
    """同步启动服务（若未运行）。返回 (success, port)"""
    if service_is_running():
        return True, CONFIG.get('port', 5000)
    service_state['stop_event'] = None
    service_state['ready'] = threading.Event()
    service_state['running'] = False
    t = threading.Thread(target=_start_service_inner, daemon=True, name='catdb-service')
    service_state['thread'] = t
    t.start()
    service_state['ready'].wait(timeout=15)
    return service_state['running'], CONFIG.get('port', 5000)

def stop_service_now():
    """同步停止服务。返回是否已停止"""
    loop = service_state.get('loop')
    stop_ev = service_state.get('stop_event')
    if loop and stop_ev is not None and not loop.is_closed():
        try:
            loop.call_soon_threadsafe(stop_ev.set)
        except Exception:
            pass
    t = service_state['thread']
    # 若在服务线程内部调用（HTTP 动作 / 请求处理器），不能 join 自己，仅发信号
    cur = threading.current_thread()
    if t is not None and t is not cur and t.is_alive():
        t.join(timeout=8)
    service_state['running'] = False
    return True

# ============== 系统托盘 ==============
tray_icon = None
_tray_active = False       # 系统托盘是否创建成功（决定点 X 是否拦截为「最小化到托盘」）
_gui_window = None         # GUI 模式窗口引用（托盘「打开面板」优先还原该窗口）
_allow_exit = False        # 置 True 后放行真正退出（托盘/界面「退出」时设置）
_SINGLE_INSTANCE_MUTEX = None


def _on_gui_window_closing():
    """窗口关闭拦截：点 X → 取消关闭、隐藏到系统托盘继续运行；
    仅当 _allow_exit=True（用户从托盘或界面选择「退出」）时才放行真正关闭。"""
    if _allow_exit:
        return
    try:
        w = _gui_window
        if w is not None:
            w.hide()
        logger.info('窗口已最小化到系统托盘（右键托盘图标可「退出」）')
    except Exception as e:
        logger.warning('隐藏窗口到托盘失败: %s', e)
    return False  # 取消本次关闭


def _show_gui_window():
    """把已最小化的 GUI 窗口恢复到前台（pystray 回调线程调用；异常则降级浏览器）"""
    w = _gui_window
    if w is None:
        return False
    try:
        w.restore()
        w.show()
        return True
    except Exception:
        return False


def update_tray_status(status_text, icon_path=None):
    global tray_icon
    if tray_icon is None:
        return
    try:
        if icon_path:
            from PIL import Image
            tray_icon.icon = Image.open(icon_path)
        tray_icon.title = f'豆包喵喵 - {status_text}'
    except Exception:
        pass

def on_tray_open(icon, item):
    # GUI 模式：把已最小化的窗口恢复到前台；纯托盘模式：浏览器打开面板
    if _show_gui_window():
        return
    try:
        webbrowser.open(f'http://127.0.0.1:{CONFIG.get("port", 5000)}/desktop.html')
    except Exception:
        pass

def on_tray_qr(icon, item):
    try:
        webbrowser.open(f'http://127.0.0.1:{CONFIG.get("port", 5000)}/qr')
    except Exception:
        pass

def on_tray_show_ip(icon, item):
    ip = get_local_ip()
    port = CONFIG.get('port', 5000)
    logger.info('📱 手机访问: http://%s:%d', ip, port)
    update_tray_status(f'http://{ip}:{port}')

def on_tray_exit(icon, item):
    global _allow_exit
    logger.info('用户请求退出，正在关闭...')
    _allow_exit = True  # 放行窗口真正关闭
    if service_is_running():
        stop_service_now()
    try:
        icon.stop()
    except Exception:
        pass
    try:
        w = _gui_window
        if w is not None:
            w.destroy()
    except Exception:
        pass
    if main_loop and not main_loop.is_closed():
        try:
            main_loop.call_soon_threadsafe(main_loop.stop)
        except Exception:
            pass
    os._exit(0)

def create_tray_icon():
    """创建系统托盘图标（菜单项避免 tkinter，二维码直接打开浏览器）"""
    global tray_icon, _tray_active
    try:
        import pystray
        from PIL import Image, ImageDraw
        img = Image.new('RGBA', (64, 64), (255, 183, 77, 255))
        draw = ImageDraw.Draw(img)
        draw.ellipse([16, 24, 48, 56], fill='#5D4037')
        draw.ellipse([12, 12, 24, 24], fill='#5D4037')
        draw.ellipse([24, 8, 36, 20], fill='#5D4037')
        draw.ellipse([36, 12, 48, 24], fill='#5D4037')
        draw.ellipse([20, 30, 44, 52], fill='#FFE0B2')

        menu = pystray.Menu(
            pystray.MenuItem('🌐 打开面板', on_tray_open, default=True),
            pystray.MenuItem('📱 显示二维码', on_tray_qr),
            pystray.MenuItem('📋 显示 IP', on_tray_show_ip),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('退出', on_tray_exit),
        )
        tray_icon = pystray.Icon('catdb', img, '豆包喵喵 - 服务运行中', menu)
        threading.Thread(target=tray_icon.run, daemon=True).start()
        _tray_active = True
        logger.info('🐾 系统托盘已启动')
        return True
    except Exception as e:
        logger.warning('创建系统托盘失败（不影响主服务）: %s', e)
        return False

# ============== 主入口（--minimized / 托盘静默模式） ==============
def run_tray_mode():
    ok, port = start_service_now()
    if not ok:
        logger.error('服务启动失败，请检查端口占用后重试')
        return
    create_tray_icon()
    # 主线程保持存活（托盘图标由子线程驱动，这里轮询避免退出）
    try:
        while service_state['running']:
            time.sleep(1.0)
    except KeyboardInterrupt:
        pass
    finally:
        stop_service_now()

# ============== 桌面 GUI 集成 ==============
class WebviewAPI:
    """给 pywebview 暴露的 API（真实控制服务；逻辑与 HTTP JSON API 共用共享辅助）"""

    def start_service(self):
        ok, port = start_service_now()
        if ok:
            logger.info('服务已启动，端口 %d', port)
        return build_status_payload()

    def stop_service(self):
        stop_service_now()
        logger.info('服务已停止')
        return build_status_payload()

    def get_service_status(self):
        return build_status_payload()

    def get_auto_start(self):
        return {"success": True, "enabled": bool(load_catdb_config().get('auto_start', False))}

    def get_autostart_status(self):
        return self.get_auto_start()

    def toggle_autostart(self, enabled):
        return self.set_auto_start(enabled)

    def set_auto_start(self, enabled):
        try:
            cfg = load_catdb_config()
            cfg['auto_start'] = bool(enabled)
            save_catdb_config(cfg)
            registry_set_autostart(bool(enabled))
            logger.info('开机自启：%s', '开启' if enabled else '关闭')
            return {"success": True, "enabled": bool(enabled)}
        except Exception as e:
            logger.error('设置开机自启失败: %s', e)
            return {"success": False, "error": str(e)}

    def get_ip_list(self):
        return {"success": True, "ips": list_ips()}

    def get_port(self):
        return {"success": True, "port": CONFIG.get('port', 5000)}

    def get_hotkey(self):
        return {"success": True, "hotkey": CONFIG.get('hotkey', 'f9')}

    def set_hotkey(self, hotkey):
        hk = str(hotkey or '').strip().lower()
        if not hk:
            return {"success": False, "error": "快捷键不能为空"}
        CONFIG['hotkey'] = hk
        cfg = load_catdb_config()
        cfg['hotkey'] = hk
        save_catdb_config(cfg)
        if service_is_running():
            setup_hotkey()  # 运行中立即重建监听；未运行时下次启动自动生效
        logger.info('清屏快捷键已设置为: [%s]', hk)
        return {"success": True, "hotkey": hk}

    def toggle_touchpad(self, enabled):
        global touchpad_enabled
        touchpad_enabled = bool(enabled)
        cfg = load_catdb_config()
        cfg['touchpad_enabled'] = touchpad_enabled
        save_catdb_config(cfg)
        logger.info('触控板模式: %s', '开启' if touchpad_enabled else '关闭')
        return {"success": True, "touchpad_enabled": touchpad_enabled}

    def get_desktop_theme(self):
        """桌面端深浅色主题（存 %APPDATA%/CatDB/config.json，重启/换端口均保留）"""
        return {"success": True, "theme": str(load_catdb_config().get('desktop_theme') or '')}

    def set_desktop_theme(self, theme):
        theme = str(theme or '').strip().lower()
        if theme not in ('light', 'dark'):
            return {"success": False, "error": "theme must be light/dark"}
        cfg = load_catdb_config()
        cfg['desktop_theme'] = theme
        save_catdb_config(cfg)
        logger.info('桌面主题：%s', '深色' if theme == 'dark' else '浅色')
        return {"success": True, "theme": theme}

    def copy_to_clipboard(self, text):
        try:
            pyperclip.copy(str(text))
            return {"success": True}
        except Exception as e:
            logger.error('复制失败: %s', e)
            return {"success": False, "error": str(e)}

    def refresh_qr(self):
        return {"success": True}

    def open_shortcut_settings(self):
        return {"success": True}

    def get_recent_logs(self):
        return {"success": True, "logs": read_log_buffer()}

    def clear_logs(self):
        clear_log_buffer()
        return {"success": True}

    def minimize_window(self):
        try:
            for w in (webview.windows or []):
                w.minimize()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def exit_app(self):
        """退出：放行窗口关闭 → 停服务 → 销毁窗口（与托盘退出等价）"""
        global _allow_exit
        try:
            _allow_exit = True
            if service_is_running():
                stop_service_now()
            for w in (webview.windows or []):
                try:
                    w.destroy()
                except Exception:
                    pass
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def hide_window(self):
        """最小化到系统托盘（进程保留，可从托盘恢复）"""
        try:
            _allow_exit = False  # 确保之后点 X 仍是「最小化到托盘」
            w = _gui_window
            if w is not None:
                w.hide()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

# API 实例（在 GUI 模式使用）
webview_api = WebviewAPI()


# ============== 启动进度条（纯 Win32 ctypes，零第三方依赖） ==============
# 双击 EXE 后立刻弹出品牌色启动窗口，进度条随真实启动阶段推进，
# 主窗口真正显示（shown 事件）后自动到 100% 并关闭 —— 避免双击后长时间无反馈。
_launch_splash = None


class LaunchSplash:
    """原生无边框置顶小窗：标题 + 阶段文字 + 平滑进度条。
    在独立线程跑消息循环，set() 只更新共享状态，由窗口定时器拉取重绘，线程安全。"""
    def __init__(self):
        self._lock = threading.Lock()
        self._hwnd = None
        self._bar = None
        self._label = None
        self._pct_label = None
        self._percent = 0
        self._text = '正在启动…'
        self._ready = threading.Event()

    # ---- 供主线程调用 ----
    def show(self):
        if platform.system() != 'Windows':
            return False
        try:
            threading.Thread(target=self._win_main, daemon=True).start()
            return self._ready.wait(timeout=5.0)
        except Exception:
            return False

    def set(self, percent, text=''):
        with self._lock:
            self._percent = max(0, min(100, int(percent)))
            if text:
                self._text = text

    def close(self):
        with self._lock:
            hwnd = self._hwnd
            self._hwnd = None
        if hwnd:
            try:
                import ctypes
                ctypes.windll.user32.PostMessageW(ctypes.c_void_p(hwnd), 0x0010, 0, 0)  # WM_CLOSE
            except Exception:
                pass

    # ---- Win32 窗口线程 ----
    def _win_main(self):
        try:
            import ctypes
            from ctypes import wintypes as wt
            user32 = ctypes.windll.user32
            gdi32 = ctypes.windll.gdi32
            kernel32 = ctypes.windll.kernel32

            WNDPROC = ctypes.WINFUNCTYPE(wt.LPARAM, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)

            # ---- 函数原型（显式 argtypes/restype，避免 64 位句柄被截断） ----
            def P(fn, restype, *args):
                fn.restype = restype
                fn.argtypes = list(args)

            P(user32.CreateWindowExW, wt.HWND, wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD,
              ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
              wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID)
            P(user32.DefWindowProcW, wt.LPARAM, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
            P(user32.DestroyWindow, wt.BOOL, wt.HWND)
            P(user32.PostQuitMessage, None, ctypes.c_int)
            P(user32.SetTimer, ctypes.c_size_t, wt.HWND, ctypes.c_size_t, wt.UINT, wt.LPVOID)
            P(user32.PostMessageW, wt.BOOL, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
            P(user32.SendMessageW, wt.LPARAM, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
            P(user32.SetWindowTextW, wt.BOOL, wt.HWND, wt.LPCWSTR)
            P(user32.ShowWindow, wt.BOOL, wt.HWND, ctypes.c_int)
            P(user32.UpdateWindow, wt.BOOL, wt.HWND)
            P(user32.SetForegroundWindow, wt.BOOL, wt.HWND)
            P(user32.GetSystemMetrics, ctypes.c_int, ctypes.c_int)
            P(user32.GetDC, wt.HDC, wt.HWND)
            P(user32.ReleaseDC, ctypes.c_int, wt.HWND, wt.HDC)
            P(user32.BeginPaint, wt.HDC, wt.HWND, ctypes.c_void_p)
            P(user32.EndPaint, wt.BOOL, wt.HWND, ctypes.c_void_p)
            P(user32.GetClientRect, wt.BOOL, wt.HWND, ctypes.c_void_p)
            P(user32.InvalidateRect, wt.BOOL, wt.HWND, ctypes.c_void_p, wt.BOOL)
            P(kernel32.GetModuleHandleW, wt.HINSTANCE, wt.LPCWSTR)
            P(gdi32.CreateSolidBrush, wt.HBRUSH, wt.DWORD)
            P(gdi32.SelectObject, wt.HGDIOBJ, wt.HDC, wt.HGDIOBJ)
            P(gdi32.GetStockObject, wt.HGDIOBJ, ctypes.c_int)
            P(gdi32.CreateFontW, wt.HFONT,
              ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
              wt.DWORD, wt.DWORD, wt.DWORD, wt.DWORD, wt.DWORD, wt.DWORD, wt.DWORD, wt.DWORD, wt.LPCWSTR)
            P(gdi32.SetTextColor, wt.COLORREF, wt.HDC, wt.COLORREF)
            P(gdi32.SetBkColor, wt.COLORREF, wt.HDC, wt.COLORREF)
            P(gdi32.GetDeviceCaps, ctypes.c_int, wt.HDC, ctypes.c_int)
            P(gdi32.RoundRect, wt.BOOL, wt.HDC,
              ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int)
            P(gdi32.SaveDC, ctypes.c_int, wt.HDC)
            P(gdi32.RestoreDC, wt.BOOL, wt.HDC, ctypes.c_int)
            P(gdi32.IntersectClipRect, ctypes.c_int, wt.HDC,
              ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int)

            class _WNDCLASSEXW(ctypes.Structure):
                _fields_ = [
                    ('cbSize', wt.UINT), ('style', wt.UINT),
                    ('lpfnWndProc', WNDPROC), ('cbClsExtra', ctypes.c_int), ('cbWndExtra', ctypes.c_int),
                    ('hInstance', wt.HINSTANCE), ('hIcon', wt.HICON), ('hCursor', ctypes.c_void_p),
                    ('hbrBackground', wt.HBRUSH), ('lpszMenuName', wt.LPCWSTR), ('lpszClassName', wt.LPCWSTR),
                    ('hIconSm', wt.HICON),
                ]

            class _PAINTSTRUCT(ctypes.Structure):
                _fields_ = [
                    ('hdc', wt.HDC), ('fErase', wt.BOOL),
                    ('rcPaint', wt.RECT), ('fRestore', wt.BOOL), ('fIncUpdate', wt.BOOL),
                    ('rgbReserved', ctypes.c_ubyte * 32),
                ]

            # 配色：白色圆角卡片 + 深棕标题 + 暖灰说明 + 品牌橙进度条
            WHITE = 0x00FFFFFF     # 主卡片底
            TRACK = 0x00D9E7F1     # RGB(241,231,218) 进度轨道（暖灰）
            FILL = 0x003D8AFF      # RGB(255,138,61) 品牌橙
            TITLE_C = 0x0020324E   # RGB(78,50,32) 标题深棕
            SUB_C = 0x0066809B     # RGB(155,128,102) 说明暖灰
            CLASS = 'CatDBLaunchSplash'
            BAR_CLASS = 'CatDBProgressSplash'

            brush = gdi32.CreateSolidBrush(WHITE)
            brush_track = gdi32.CreateSolidBrush(TRACK)
            brush_fill = gdi32.CreateSolidBrush(FILL)
            null_pen = gdi32.GetStockObject(8)  # NULL_PEN
            hinst = kernel32.GetModuleHandleW(None)

            # 字体（按 DPI 缩放）
            dc = user32.GetDC(None)
            dpi = gdi32.GetDeviceCaps(dc, 88)  # LOGPIXELSX
            user32.ReleaseDC(None, dc)
            scale = max(1.0, dpi / 96.0)

            def mkfont(px, weight):
                return gdi32.CreateFontW(-int(px * scale), 0, 0, 0, weight, 0, 0, 0,
                                         1, 0, 0, 5, 0, 'Microsoft YaHei UI')
            font_title = mkfont(17, 700)
            font_sub = mkfont(11, 400)

            w, h = int(380 * scale), int(128 * scale)
            x = (user32.GetSystemMetrics(0) - w) // 2
            y = (user32.GetSystemMetrics(1) - h) // 3

            state = self

            @WNDPROC
            def bar_proc(hwnd, msg, wp, lp):
                """自绘圆角进度条：暖灰轨道 + 品牌橙填充（Real 高 DPI 平滑圆角）"""
                if msg == 0x000F:  # WM_PAINT
                    ps = _PAINTSTRUCT()
                    hdc = user32.BeginPaint(hwnd, ctypes.byref(ps))
                    try:
                        rc = wt.RECT()
                        user32.GetClientRect(hwnd, ctypes.byref(rc))
                        bw, bh = rc.right - rc.left, rc.bottom - rc.top
                        with state._lock:
                            pct = state._percent
                        gdi32.SelectObject(hdc, null_pen)
                        gdi32.SelectObject(hdc, brush_track)
                        gdi32.RoundRect(hdc, 0, 0, bw, bh, bh, bh)
                        if pct > 0:
                            fill_w = max(bh // 2, int(bw * pct / 100))
                            saved = gdi32.SaveDC(hdc)
                            gdi32.IntersectClipRect(hdc, 0, 0, fill_w, bh)
                            gdi32.SelectObject(hdc, brush_fill)
                            gdi32.RoundRect(hdc, 0, 0, bw, bh, bh, bh)
                            gdi32.RestoreDC(hdc, saved)
                    finally:
                        user32.EndPaint(hwnd, ctypes.byref(ps))
                    return 0
                return user32.DefWindowProcW(hwnd, msg, wp, lp)

            @WNDPROC
            def wnd_proc(hwnd, msg, wp, lp):
                if msg == 0x0010:  # WM_CLOSE
                    user32.DestroyWindow(hwnd)
                    return 0
                if msg == 0x0002:  # WM_DESTROY
                    with state._lock:
                        state._hwnd = None
                    user32.PostQuitMessage(0)
                    return 0
                if msg == 0x0084:  # WM_NCHITTEST：整窗可拖动
                    return 2  # HTCAPTION
                if msg == 0x0113:  # WM_TIMER（每 50ms 拉取最新进度）
                    with state._lock:
                        pct, txt = state._percent, state._text
                    if state._bar:
                        user32.InvalidateRect(state._bar, None, False)
                    if state._label:
                        user32.SetWindowTextW(state._label, txt)
                    if state._pct_label:
                        user32.SetWindowTextW(state._pct_label, f'{pct}%')
                    return 0
                if msg == 0x0138:  # WM_CTLCOLORSTATIC：文字配色
                    hdc = wp
                    child_hwnd = lp
                    if child_hwnd == title:
                        gdi32.SetTextColor(hdc, TITLE_C)
                    else:
                        gdi32.SetTextColor(hdc, SUB_C)
                    gdi32.SetBkColor(hdc, WHITE)
                    return brush
                return user32.DefWindowProcW(hwnd, msg, wp, lp)

            wc = _WNDCLASSEXW()
            wc.cbSize = ctypes.sizeof(_WNDCLASSEXW)
            wc.style = 0x00020000  # CS_DROPSHADOW（柔和投影）
            wc.lpfnWndProc = wnd_proc
            wc.cbClsExtra = 0
            wc.cbWndExtra = 0
            wc.hInstance = hinst
            wc.hIcon = None
            wc.hCursor = None
            wc.hbrBackground = brush
            wc.lpszMenuName = None
            wc.lpszClassName = CLASS
            wc.hIconSm = None
            if not user32.RegisterClassExW(ctypes.byref(wc)):
                return

            bc = _WNDCLASSEXW()
            bc.cbSize = ctypes.sizeof(_WNDCLASSEXW)
            bc.style = 0
            bc.lpfnWndProc = bar_proc
            bc.cbClsExtra = 0
            bc.cbWndExtra = 0
            bc.hInstance = hinst
            bc.hIcon = None
            bc.hCursor = None
            bc.hbrBackground = brush
            bc.lpszMenuName = None
            bc.lpszClassName = BAR_CLASS
            bc.hIconSm = None
            if not user32.RegisterClassExW(ctypes.byref(bc)):
                return

            hwnd = user32.CreateWindowExW(
                0x00000008 | 0x00000080,  # WS_EX_TOPMOST | WS_EX_TOOLWINDOW
                CLASS, '豆包喵喵 正在启动…',
                0x80000000,  # WS_POPUP（无边框，投影由 CS_DROPSHADOW + DWM 圆角提供）
                x, y, w, h, None, None, hinst, None)
            if not hwnd:
                return

            # Win11 圆角
            try:
                dwm = ctypes.WinDLL('dwmapi')
                corner = ctypes.c_int(2)  # DWMWCP_ROUND
                dwm.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(corner), ctypes.sizeof(corner))
            except Exception:
                pass

            with state._lock:
                state._hwnd = hwnd

            # 标题 / 阶段说明 / 百分比 / 自绘进度条（简洁分区布局）
            def child(cls, text, rect, font, style=0):
                # rect = (left, top, right, bottom)；转为 CreateWindowExW 的 (x, y, cx, cy)
                l, t, r, b = rect
                hc = user32.CreateWindowExW(
                    0, cls, text,
                    0x40000000 | 0x10000000 | style,  # WS_CHILD | WS_VISIBLE | style
                    l, t, r - l, b - t, hwnd, None, hinst, None)
                if hc and font:
                    user32.SendMessageW(hc, 0x0030, font, 1)  # WM_SETFONT
                return hc

            title = child('STATIC', '豆包喵喵',
                          (int(26 * scale), int(18 * scale), w - int(26 * scale), int(52 * scale)),
                          font_title)
            label = child('STATIC', '正在启动…',
                          (int(26 * scale), int(54 * scale), w - int(110 * scale), int(76 * scale)),
                          font_sub)
            pct_label = child('STATIC', '0%',
                              (w - int(110 * scale), int(54 * scale), w - int(26 * scale), int(76 * scale)),
                              font_sub, style=0x0002)  # SS_RIGHT
            bar = child(BAR_CLASS, None,
                        (int(26 * scale), int(92 * scale), w - int(26 * scale), int(92 * scale) + int(8 * scale)),
                        None)

            with state._lock:
                state._label = label
                state._pct_label = pct_label
                state._bar = bar

            user32.ShowWindow(hwnd, 5)  # SW_SHOW
            user32.UpdateWindow(hwnd)
            user32.SetForegroundWindow(hwnd)
            user32.SetTimer(hwnd, 1, 50, None)
            state._ready.set()

            # 看门狗：最长 25s 强制关闭（防止主窗口 shown 事件缺失导致残留）
            threading.Timer(25.0, state.close).start()

            msg = wt.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        except Exception as e:
            try:
                logger.warning('启动进度条创建失败（不影响使用）: %s', e)
            except Exception:
                pass
        finally:
            self._ready.set()


def splash_show():
    """弹出启动进度条（幂等；非 Windows/失败时静默返回 False）"""
    global _launch_splash
    if _launch_splash is None:
        _launch_splash = LaunchSplash()
    return _launch_splash.show()


def splash_set(percent, text=''):
    if _launch_splash is not None:
        _launch_splash.set(percent, text)


def splash_close():
    global _launch_splash
    if _launch_splash is not None:
        _launch_splash.close()
        _launch_splash = None


def _on_main_window_shown():
    """主窗口真正显示：进度条到 100% 并关闭"""
    splash_set(100, '启动完成')
    splash_close()


# ============== 单实例检测（防多开） ==============
def _acquire_single_instance():
    """Windows 命名互斥体防止多开：已有一个客户端运行时，
    第二个实例弹窗提示「你已经开了一个客户端了」并退出。"""
    global _SINGLE_INSTANCE_MUTEX
    if platform.system() != 'Windows':
        return True
    try:
        import ctypes
        k32 = ctypes.WinDLL('kernel32', use_last_error=True)
        _SINGLE_INSTANCE_MUTEX = k32.CreateMutexW(None, False,
                                                  'CatDB_Desktop_SingleInstance')
        if not _SINGLE_INSTANCE_MUTEX:
            return True
        if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
            try:
                ctypes.windll.user32.MessageBoxW(
                    0,
                    '你已经开了一个客户端了。\n\n豆包喵喵已在运行，请勿重复启动。',
                    '豆包喵喵', 0x40)  # MB_ICONINFORMATION
            except Exception:
                pass
            return False
        return True
    except Exception:
        return True  # 拿不到锁（非 Windows）时放行，避免锁机制导致无法启动


# ============== GUI / 托盘双模式启动入口 ==============
def run_gui_mode():
    """桌面 GUI 模式：先启动后端服务，再打开本地加载的 desktop.html 窗口。
    页面由本地文件提供（不依赖 127.0.0.1 的 HTTP），彻底规避端口猜测/竞态导致的 404。"""
    global main_loop
    if webview is None:
        logger.error('缺少 pywebview，无法启动桌面界面。请执行: pip install pywebview')
        return

    # 启动进度条：双击后立即给出视觉反馈，主窗口真正显示后自动关闭
    splash_show()
    splash_set(5, '正在初始化…')
    ok, port = start_service_now()
    if ok:
        splash_set(28, '本地服务已就绪')
    else:
        splash_set(28, '本地服务未启动（可稍后手动启动）')
        logger.warning('后端服务未能自动启动，界面将以“未运行”状态打开（可手动点击启动）')

    # pywebview 加载本地文件：file:// URL，路径含空格/中文也安全
    try:
        import pathlib
        desktop = pathlib.Path(_resource_path(os.path.join('www', 'desktop.html')))
        url = desktop.as_uri()
    except Exception:
        url = f'http://127.0.0.1:{CONFIG.get("port", 5000)}/desktop.html'

    splash_set(45, '正在创建界面窗口…')
    global _gui_window
    try:
        _gui_window = webview.create_window(
            "豆包喵喵",
            url,
            width=960,
            height=680,
            min_size=(820, 620),
            resizable=True,
            js_api=webview_api,
            background_color='#F5F5F7',
        )
    except Exception as e:
        # 原生窗口创建失败时降级：浏览器打开桌面页 + 托盘常驻，保证功能可用
        logger.error('创建桌面窗口失败，已降级为浏览器模式: %s', e)
        try:
            webbrowser.open(f'http://127.0.0.1:{CONFIG.get("port", 5000)}/desktop.html')
        except Exception:
            pass
        splash_close()
        run_tray_mode()
        return

    splash_set(62, '界面窗口已创建')
    # 主窗口真正显示时：进度条到 100% 并关闭启动画面
    try:
        _gui_window.events.shown += _on_main_window_shown
    except Exception as e:
        logger.warning('绑定主窗口 shown 事件失败（启动画面将由看门狗兜底关闭）: %s', e)

    # 系统托盘 + 「关闭窗口 → 最小化到托盘」
    # （托盘创建失败则保持原「关闭即退出」行为，避免窗口隐藏后无法恢复）
    if create_tray_icon() and _gui_window is not None:
        try:
            _gui_window.events.closing += _on_gui_window_closing
            logger.info('已启用：点关闭按钮将最小化到系统托盘')
        except Exception as e:
            logger.warning('绑定窗口关闭拦截失败，保持原退出行为: %s', e)

    splash_set(88, '正在加载界面…')
    logger.info('启动耗时：从进程启动到窗口就绪 %.0f ms',
                (time.time() - _APP_START_TS) * 1000)
    try:
        webview.start(debug=False)
    finally:
        splash_close()
        # 窗口关闭后停止后端，避免残留进程占端口
        if service_is_running():
            stop_service_now()
        logger.info('👋 喵喵休息了')

def main():
    init_file_logging()
    logger.info('启动阶段：模块导入耗时 %.0f ms', (time.time() - _APP_START_TS) * 1000)
    if not _acquire_single_instance():
        sys.exit(0)  # 已有一个客户端，弹窗提示后退出
    parse_args()
    load_persisted_prefs()
    minimized = CONFIG.get('minimized', False)
    if minimized:
        run_tray_mode()
    else:
        run_gui_mode()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.info('👋 喵喵休息了')
        try:
            stop_service_now()
        except Exception:
            pass
        sys.exit(0)
    except Exception as e:
        logger.error('启动失败: %s', e)
        sys.exit(1)
