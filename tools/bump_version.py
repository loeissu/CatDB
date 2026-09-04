#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""统一版本号升级脚本。

一处调用，同步更新所有版本号位置（server.py / package.json /
capacitor.config.json / android build.gradle / www/desktop.html），
避免「打包版本已升、客户端显示旧版本」的问题。

用法：
    python tools/bump_version.py <版本> <versionCode>
示例：
    python tools/bump_version.py 2.2.12 14
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(rel):
    p = os.path.join(ROOT, rel)
    with open(p, encoding='utf-8', newline='') as f:  # newline='' 保留原始换行符
        return f.read()


def write(rel, s):
    p = os.path.join(ROOT, rel)
    with open(p, 'w', encoding='utf-8', newline='') as f:  # 不翻译换行，保持原样
        f.write(s)
    print(f'updated: {rel}')


def replace(rel, pattern, repl, count=1):
    s = read(rel)
    new, n = re.subn(pattern, repl, s, count=count)
    if n == 0:
        raise SystemExit(f'[{rel}] 未匹配: {pattern}')
    write(rel, new)


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    ver, code = sys.argv[1], sys.argv[2]
    if not re.fullmatch(r'\d+\.\d+\.\d+', ver):
        raise SystemExit(f'版本号格式错误: {ver!r}（应为 x.y.z）')
    if not code.isdigit():
        raise SystemExit(f'versionCode 必须为数字: {code!r}')

    # 服务端（桌面客户端显示的版本号来源）
    replace('server.py', r'__version__ = "\d+\.\d+\.\d+"', f'__version__ = "{ver}"')
    # 桌面端 HTML 兜底显示
    replace('www/desktop.html', r"version: '\d+\.\d+\.\d+'", f"version: '{ver}'")
    replace('www/desktop.html', r"\|\| '\d+\.\d+\.\d+'", f"|| '{ver}'")
    replace('www/desktop.html', r'v\d+\.\d+\.\d+</span>', f'v{ver}</span>')
    # Node/Capacitor 配置
    replace('package.json', r'"version": "\d+\.\d+\.\d+"', f'"version": "{ver}"')
    replace('capacitor.config.json', r'"version": "\d+\.\d+\.\d+"', f'"version": "{ver}"', count=2)
    replace('capacitor.config.json', r'"appVersion": "\d+\.\d+\.\d+"', f'"appVersion": "{ver}"')
    # Android 原生
    replace('android/app/build.gradle', r'versionCode \d+', f'versionCode {code}')
    replace('android/app/build.gradle', r'versionName "\d+\.\d+\.\d+"', f'versionName "{ver}"')

    print(f'OK: 全部版本号已同步为 {ver} (versionCode {code})')


if __name__ == '__main__':
    main()