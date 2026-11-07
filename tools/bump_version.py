#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""统一版本号升级（v2.3.0 起已移除安卓客户端，不再有 versionCode）。

用法：python tools/bump_version.py <版本>     例如 2.3.1
同步位置：server.py / www/desktop.html / package.json
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def replace(rel, pattern, repl, count=1):
    p = os.path.join(ROOT, rel)
    with open(p, encoding='utf-8', newline='') as f:
        s = f.read()
    new, n = re.subn(pattern, repl, s, count=count)
    if n == 0:
        raise SystemExit('[%s] 未匹配: %s' % (rel, pattern))
    with open(p, 'w', encoding='utf-8', newline='') as f:
        f.write(new)
    print('updated:', rel)


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    ver = sys.argv[1]
    if not re.fullmatch(r'\d+\.\d+\.\d+', ver):
        raise SystemExit('版本号格式错误: %r（应为 x.y.z）' % ver)
    replace('server.py', r'__version__ = "\d+\.\d+\.\d+"', '__version__ = "%s"' % ver)
    replace('www/desktop.html', r"version: '\d+\.\d+\.\d+'", "version: '%s'" % ver)
    replace('www/desktop.html', r"\|\| '\d+\.\d+\.\d+'", "|| '%s'" % ver)
    replace('www/desktop.html', r'v\d+\.\d+\.\d+</span>', 'v%s</span>' % ver)
    replace('package.json', r'"version": "\d+\.\d+\.\d+"', '"version": "%s"' % ver)
    print('OK: 全部版本号已同步为 %s' % ver)


if __name__ == '__main__':
    main()
