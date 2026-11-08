# -*- coding: utf-8 -*-
"""豆包喵喵 / CatDB 回归测试（v2.3.0 重写）。

设计约束：
* 只用 Python 标准库，CI 在 `pip install` 之前即可运行；
* 不依赖 GUI、网络、管理员权限，也不修改真实用户配置；
* 每个用例对应一处已修复的 bug 或一条新行为，失败即阻断打包。

运行：python -m unittest discover -s tests -v
"""
import asyncio
import importlib.util
import inspect
import io
import json
import os
import re
import shlex
import sys
import types
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER = os.path.join(ROOT, 'server.py')


def read(rel):
    with io.open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        return f.read()


# --------------------------------------------------------------------------
# 用最小 stub 载入 server.py（CI 装依赖前 / 本机未装依赖时都不会 ImportError）
# --------------------------------------------------------------------------
def _load_server():
    if importlib.util.find_spec('aiohttp') is None:
        aiohttp = types.ModuleType('aiohttp')
        web = types.ModuleType('aiohttp.web')

        class _Stub:
            def __init__(self, *a, **kw):
                self.args, self.kw = a, kw

        for name in ('WebSocketResponse', 'Response', 'Application', 'AppRunner', 'TCPSite'):
            setattr(web, name, _Stub)
        web.json_response = lambda *a, **kw: None
        aiohttp.web = web
        aiohttp.WSMsgType = types.SimpleNamespace(TEXT=1, ERROR=2, BINARY=3, CLOSE=4)
        sys.modules['aiohttp'] = aiohttp
        sys.modules['aiohttp.web'] = web
    if importlib.util.find_spec('pyperclip') is None:
        pc = types.ModuleType('pyperclip')
        pc.paste = lambda: ''
        pc.copy = lambda text: None
        sys.modules['pyperclip'] = pc
    spec = importlib.util.spec_from_file_location('catdb_under_test', SERVER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


srv = _load_server()


class FakeReq:
    def __init__(self, query=None, remote='127.0.0.1'):
        self.query = query or {}
        self.remote = remote


class CatDBTestCase(unittest.TestCase):
    """统一保存/恢复被用例修改的全局状态，避免顺序依赖。"""

    def setUp(self):
        self._saved = {
            'AUTH_TOKEN': srv.AUTH_TOKEN,
            'CONFIG': dict(srv.CONFIG),
            'synced_text': srv.synced_text,
            'pending_strip_punctuation': srv.pending_strip_punctuation,
            'rebase_triggered': srv.rebase_triggered,
            'touchpad_enabled': srv.touchpad_enabled,
            '_allow_exit': srv._allow_exit,
        }
        srv.AUTH_TOKEN = 'test-token-123'   # 固定测试连接码，不触碰真实 %APPDATA%
        srv.CONFIG['hotkey'] = None
        srv.CONFIG['port'] = 5000

    def tearDown(self):
        for k, v in self._saved.items():
            setattr(srv, k, dict(v) if k == 'CONFIG' else v)


# ==========================================================================
# 一、版本 / 工程结构 / 语法
# ==========================================================================
class TestProjectIntegrity(CatDBTestCase):

    def test_all_python_files_compile(self):
        """所有 .py 必须可编译（旧版 6 个 UTF-16 辅助脚本已清理）。"""
        checked = 0
        for base, _dirs, files in os.walk(ROOT):
            if '.git' in base or '__pycache__' in base:
                continue
            for fn in files:
                if not fn.endswith('.py'):
                    continue
                p = os.path.join(base, fn)
                with io.open(p, encoding='utf-8') as f:
                    compile(f.read(), p, 'exec')
                checked += 1
        self.assertGreaterEqual(checked, 3)

    def test_version_is_consistent_everywhere(self):
        ver = srv.__version__
        self.assertRegex(ver, r'^\d+\.\d+\.\d+$')
        self.assertEqual(json.loads(read('package.json'))['version'], ver)
        desk = read('www/desktop.html')
        self.assertIn("version: '%s'" % ver, desk)
        self.assertIn("|| '%s'" % ver, desk)
        self.assertIn('v%s</span>' % ver, desk)
        self.assertIn('__version__ = "%s"' % ver, read('server.py'))

    def test_android_client_is_gone(self):
        for rel in ('android', 'capacitor.config.json', 'www/vendor',
                    'generate_icons.js', '豆包喵喵.spec'):
            self.assertFalse(os.path.exists(os.path.join(ROOT, rel)), '%s 仍存在' % rel)
        self.assertNotIn('src="vendor/', read('www/index.html'))
        self.assertNotIn('capacitor.config.json', read('tools/bump_version.py'))
        self.assertNotIn('android/app/build.gradle', read('tools/bump_version.py'))
        self.assertIn('不再提供安卓原生 App', read('README.md'))

    def test_single_packaging_entry_and_ci_gate(self):
        self.assertIn("('www', 'www')", read('CatDB.spec'))
        self.assertIn('pyinstaller CatDB.spec', read('build_portable.bat'))
        yml = read('.github/workflows/build.yml')
        self.assertIn('unittest discover -s tests', yml)
        self.assertLess(yml.index('unittest discover -s tests'),
                        yml.index('pyinstaller CatDB.spec'), '测试必须在打包之前')


# ==========================================================================
# 二、已修复 bug 的回归
# ==========================================================================
class TestBugFixes(CatDBTestCase):

    def test_persisted_hotkey_is_restored_on_startup(self):
        with mock.patch.object(srv, 'load_catdb_config',
                               return_value={'hotkey': 'f8', 'touchpad_enabled': False}):
            srv.CONFIG['hotkey'] = None
            srv.load_persisted_prefs()
        self.assertEqual(srv.CONFIG['hotkey'], 'f8')

    def test_explicit_cli_hotkey_still_wins(self):
        with mock.patch.object(srv, 'load_catdb_config', return_value={'hotkey': 'f8'}):
            srv.CONFIG['hotkey'] = 'f6'
            srv.load_persisted_prefs()
        self.assertEqual(srv.CONFIG['hotkey'], 'f6')

    def test_hide_window_resets_global_exit_flag(self):
        self.assertNotIn('_allow_exit', srv.WebviewAPI.hide_window.__code__.co_varnames)
        srv._allow_exit = True
        srv.WebviewAPI().hide_window()
        self.assertFalse(srv._allow_exit)

    def test_port_scan_never_exceeds_firewall_range(self):
        self.assertEqual(srv.PORT_SCAN_ATTEMPTS,
                         srv.FIREWALL_PORT_HI - srv.FIREWALL_PORT_LO + 1)
        with mock.patch.object(srv, 'check_port_available',
                               side_effect=lambda host, port: port > srv.FIREWALL_PORT_HI):
            self.assertIsNone(srv.find_available_port(5000, max_attempts=20),
                              '旧实现会返回 5011，越过已放行的 5000-5010')

    def test_elevated_netsh_command_is_well_formed(self):
        cmd = srv.elevated_netsh_command()
        toks = shlex.split(cmd)
        self.assertEqual(toks[0], 'advfirewall', 'lpParameters 不能重复传 exe 名 netsh')
        self.assertIn('name=CatDB Desktop (5000-5010)', toks, '规则名必须是一个完整参数')
        self.assertIn('profile=private,domain', cmd)
        self.assertNotIn('profile=any', cmd)

    def test_firewall_detection_is_language_independent(self):
        cases = [
            ('Rule Name:              CatDB Desktop (5000-5010)\nEnabled: Yes', True),
            ('规则名称:              CatDB Desktop (5000-5010)\n已启用: 是', True),
            ('No rules match the specified criteria.', False),
            ('没有匹配指定标准的规则。', False),
        ]
        for out, expected in cases:
            r = types.SimpleNamespace(returncode=0, stdout=out, stderr='')
            with mock.patch.object(srv, '_run_netsh', return_value=r):
                self.assertEqual(srv.firewall_rule_exists(), expected, out[:30])

    def test_netsh_mixed_encoding_does_not_crash(self):
        """stdout UTF-8 可解、stderr 是 GBK 中文：旧实现会二次 decode 抛 AttributeError。"""
        r = types.SimpleNamespace(
            stdout=b'Rule Name: CatDB\n',
            stderr='请求的操作需要提升'.encode('gbk'),
            returncode=0)
        with mock.patch.object(srv.subprocess, 'run', return_value=r):
            out = srv._run_netsh(['netsh'])
        self.assertIsInstance(out.stdout, str)
        self.assertIsInstance(out.stderr, str)
        self.assertIn('请求的操作需要提升', out.stderr)

    def test_compute_diff_cases(self):
        cases = [
            ('', 'abc', 0, 'abc'),
            ('abc', 'abcd', 0, 'd'),
            ('abcd', 'abc', 1, ''),
            ('abc', 'ac', 1, ''),
            ('abc', 'xbc', 1, 'x'),
            ('abc', 'abc', 0, ''),
            ('你好', '你好吗', 0, '吗'),
        ]
        for old, new, dele, add in cases:
            self.assertEqual(srv.compute_diff(old, new), (dele, add), (old, new))

    def test_punctuation_strip_keeps_state_in_sync(self):
        """剪掉句首标点后，synced_text 必须等于屏幕上的文本，否则下一帧会误删正文。"""
        calls = {'backspaces': 0, 'typed': []}
        with mock.patch.object(srv, 'send_backspaces',
                               side_effect=lambda n: calls.__setitem__('backspaces', calls['backspaces'] + n)), \
             mock.patch.object(srv, 'type_text', side_effect=lambda t: calls['typed'].append(t)), \
             mock.patch.object(srv, 'update_live_typing', lambda t: None):
            srv.synced_text = ''
            srv.pending_strip_punctuation = True
            srv.rebase_triggered = False
            srv.apply_text_diff('，你好')
            self.assertEqual(calls['typed'], ['你好'])
            self.assertEqual(srv.synced_text, '你好')
            srv.apply_text_diff('你好')  # 手机把标点删掉
            self.assertEqual(calls['backspaces'], 0, '不应删除屏幕上的正文')

    def test_private_ip_detection_is_narrow(self):
        self.assertTrue(srv._is_private_ip('192.168.1.5'))
        self.assertTrue(srv._is_private_ip('10.0.0.1'))
        self.assertTrue(srv._is_private_ip('172.20.1.1'))
        self.assertFalse(srv._is_private_ip('192.0.2.1'))
        self.assertFalse(srv._is_private_ip('198.18.0.1'))


# ==========================================================================
# 三、v2.3.0 安全加固
# ==========================================================================
class TestSecurity(CatDBTestCase):

    def test_ws_requires_valid_connection_key(self):
        self.assertTrue(srv.ws_authorized(FakeReq({'k': 'test-token-123'})))
        self.assertFalse(srv.ws_authorized(FakeReq({'k': 'wrong'})))
        self.assertFalse(srv.ws_authorized(FakeReq({})))

    def test_http_control_api_is_loopback_only(self):
        self.assertTrue(srv.is_loopback_request(FakeReq(remote='127.0.0.1')))
        self.assertTrue(srv.is_loopback_request(FakeReq(remote='::1')))
        self.assertFalse(srv.is_loopback_request(FakeReq(remote='192.168.1.9')))
        self.assertFalse(srv.is_loopback_request(FakeReq(remote='')))

    def test_no_wildcard_cors(self):
        self.assertNotIn('Access-Control-Allow-Origin', srv.LOCAL_ONLY_HEADERS)
        self.assertNotIn('Access-Control-Allow-Origin: *', read('server.py'))

    def test_no_shell_launch_from_phone(self):
        self.assertNotIn('cmd', srv.ALLOWED_COMMANDS)
        self.assertNotIn('powershell', srv.ALLOWED_COMMANDS)
        self.assertLessEqual(len(srv.ALLOWED_COMMANDS), 3)

    def test_key_combo_whitelist(self):
        self.assertTrue(srv.validate_key_combo(['ctrl', 's']))
        self.assertTrue(srv.validate_key_combo(['alt', 'tab']))
        self.assertFalse(srv.validate_key_combo(['ctrl', 'rm', '-rf']))
        self.assertFalse(srv.validate_key_combo([]))
        self.assertFalse(srv.validate_key_combo(['f13']))

    def test_mobile_url_carries_key_and_host_is_sanitized(self):
        url = srv.mobile_url('192.168.1.5', 5000)
        self.assertIn('?k=test-token-123', url)
        self.assertTrue(url.startswith('http://192.168.1.5:5000/'))
        self.assertEqual(srv.safe_host('192.168.1.5'), '192.168.1.5')
        self.assertEqual(srv.safe_host('<script>alert(1)</script>'), '')
        self.assertEqual(srv.safe_host('a' * 500), '')


# ==========================================================================
# 四、事件循环 / 健壮性 / 新增易用性
# ==========================================================================
class TestRuntimeAndUsability(CatDBTestCase):

    def test_blocking_gui_ops_run_in_executor(self):
        src = inspect.getsource(srv.handle_websocket)
        self.assertIn('run_in_executor', src)
        self.assertNotIn('type_text(', src, '不得在事件循环里直接调用 type_text')
        self.assertNotIn('send_backspaces(', src, '不得在事件循环里直接调用 send_backspaces')
        self.assertIn('apply_text_diff', src)

    def test_bad_messages_are_isolated_not_fatal(self):
        src = inspect.getsource(srv.handle_websocket)
        self.assertIn('except (ValueError, TypeError)', src)
        self.assertIn('isinstance(new_txt, str)', src)
        self.assertIn('4401', src)

    def test_status_payload_has_diagnostics(self):
        with mock.patch.object(srv, 'get_local_ip', return_value='192.168.1.5'), \
             mock.patch.object(srv, 'list_ips', return_value=['192.168.1.5']), \
             mock.patch.object(srv, 'service_is_running', return_value=True), \
             mock.patch.object(srv, 'load_catdb_config', return_value={}):
            p = srv.build_status_payload()
        self.assertIn('?k=test-token-123', p['connect_url'])
        self.assertEqual(p['port_range'], [5000, 5010])
        self.assertIn('clients', p)
        self.assertEqual(p['version'], srv.__version__)

    def test_connect_page_renders_address_key_and_copy_button(self):
        class Capture:
            def __init__(self, *a, **kw):
                self.kw = kw

        with mock.patch.object(srv, '_make_qr_png', return_value=b'PNG'), \
             mock.patch.object(srv, 'get_local_ip', return_value='192.168.1.5'), \
             mock.patch.object(srv.web, 'Response', Capture):
            resp = asyncio.run(srv.handle_connect_page(FakeReq({'ip': '192.168.1.5'})))
        body = resp.kw['text']
        self.assertIn('?k=test-token-123', body)
        self.assertIn('连接码', body)
        self.assertIn('复制完整地址', body)
        self.assertIn('同一 Wi-Fi', body)

    def test_connect_page_escapes_host_input(self):
        class Capture:
            def __init__(self, *a, **kw):
                self.kw = kw

        with mock.patch.object(srv, '_make_qr_png', return_value=b'PNG'), \
             mock.patch.object(srv, 'get_local_ip', return_value='192.168.1.5'), \
             mock.patch.object(srv.web, 'Response', Capture):
            resp = asyncio.run(srv.handle_connect_page(
                FakeReq({'ip': '"><img src=x onerror=alert(1)>'})))
        self.assertNotIn('onerror=alert', resp.kw['text'])

    def test_startup_logs_and_tray_expose_full_address(self):
        src = read('server.py')
        self.assertIn('手机连接地址（含连接码）', src)
        self.assertIn('on_tray_copy_url', src)
        self.assertIn("/connect'", src)


# ==========================================================================
# 五、前端静态回归
# ==========================================================================
class TestFrontend(CatDBTestCase):

    def test_newline_check_uses_real_linefeed(self):
        html = read('www/index.html')
        lines = [l for l in html.splitlines() if 'input.value.includes' in l]
        self.assertEqual(len(lines), 1)
        line = lines[0]
        self.assertIn("includes('\\n')", line)
        self.assertEqual(line.count('\\'), 1, '只能是单个反斜杠转义，不能是字面 \\\\n')

    def test_phone_ws_url_carries_key(self):
        html = read('www/index.html')
        self.assertIn('connectionKey()', html)
        self.assertIn('/ws?k=', html)
        self.assertIn('e.code === 4401', html)
        self.assertIn('connectionKey', html)

    def test_phone_accepts_pasted_full_address(self):
        html = read('www/index.html')
        self.assertIn("searchParams.get('k')", html)
        self.assertIn('粘贴', html)

    def test_desktop_shows_key_and_client_count(self):
        html = read('www/desktop.html')
        self.assertIn('S.auth_token', html)
        self.assertIn('?k=', html)
        self.assertIn('台已连接', html)
        self.assertIn('S.clients', html)

    def test_no_native_statusbar_bridge_left(self):
        html = read('www/index.html')
        self.assertNotIn('syncNativeStatusBar', html)
        self.assertNotIn('CatDBStatusBar', html)
        self.assertIn("name=\"theme-color\"", html)  # PWA 主题仍保留


# ==========================================================================
# 五、输入链路隔离（v2.3.1：修复全局鼠标钩子拖慢系统鼠标）
# ==========================================================================
class TestInputPipelineIsolation(CatDBTestCase):

    def test_no_global_mouse_hook_is_installed(self):
        """pynput.mouse.Listener == SetWindowsHookEx(WH_MOUSE_LL)，绝不能再用。"""
        src = read('server.py')
        self.assertNotIn('mouse.Listener', src)
        self.assertNotIn('from pynput import keyboard, mouse', src)
        self.assertIn('GetAsyncKeyState', src)
        self.assertIn('_mouse_click_poll', src)

    def test_hook_callback_never_does_blocking_work(self):
        """钩子回调只允许投递事件；加锁 / 日志 / 广播 / 上屏一律挪到工作线程。"""
        src = inspect.getsource(srv.setup_hotkey)
        self.assertIn('_enqueue_input', src)
        for forbidden in ('reset_synced_text(', 'get_detect_keyboard_enabled(',
                          'run_coroutine_threadsafe', 'mouse.Listener', 'pyautogui'):
            self.assertNotIn(forbidden, src,
                             '钩子线程里出现阻塞操作 %r 会拖慢全系统输入' % forbidden)

    def test_blocking_work_lives_in_worker_thread(self):
        worker = inspect.getsource(srv._process_input_events)
        self.assertIn('reset_synced_text()', worker)
        self.assertIn('get_detect_keyboard_enabled()', worker)
        self.assertIn('run_coroutine_threadsafe', worker)
        # 上屏期间 _text_lock 被持有，此时注入的按键不能误判为「电脑介入」
        self.assertIn('_text_lock.acquire(blocking=False)', worker)

    def test_mouse_polling_is_hook_free_and_edge_triggered(self):
        poll = inspect.getsource(srv._mouse_click_poll)
        self.assertIn('GetAsyncKeyState', poll)
        self.assertIn('down and not prev_down', poll)
        self.assertNotIn('SetWindowsHookEx', poll)
        self.assertNotIn('Listener', poll)


if __name__ == '__main__':
    unittest.main(verbosity=2)
