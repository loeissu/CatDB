# -*- coding: utf-8 -*-
"""
矢量风格重绘安卓图标：简洁大色块橙猫（圆角底 + 粗深棕描边 + 大眼/胡须/嘴）。
小尺寸（48px）下依然清晰可读 —— 解决旧方案放大 128px 复杂图案导致模糊的问题。
生成：legacy mipmap 全套 + 自适应前景（66% 安全区）+ 背景色。
"""
import os
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(ROOT, 'android', 'app', 'src', 'main', 'res')

S = 1024                       # 主画布
O = '#4A2C1A'                  # 深棕描边
CAT = '#F59E42'                # 猫橙
INNER = '#F7C6A0'              # 内耳
BG = '#FBE8CF'                 # 米色圆角底（legacy 与自适应背景共用）
NOSE = '#4A2C1A'               # 眼鼻深棕
WHITE = '#FFFFFF'              # 高光

LEGACY_SIZES = {'mdpi': 48, 'hdpi': 72, 'xhdpi': 96, 'xxhdpi': 144, 'xxxhdpi': 192}
FG_SIZES = {'mdpi': 108, 'hdpi': 162, 'xhdpi': 216, 'xxhdpi': 324, 'xxxhdpi': 432}


def ear(d, pts):
    """三角形猫耳：先画外扩深棕描边层，再画橙色填充层（粗描边在缩放后仍圆润自然）。"""
    cx = sum(p[0] for p in pts) / 3.0
    cy = sum(p[1] for p in pts) / 3.0
    big = [(cx + (x - cx) * 1.10, cy + (y - cy) * 1.10) for x, y in pts]
    d.polygon(big, fill=O)
    d.polygon(pts, fill=CAT)


def draw_cat(with_bg):
    im = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if with_bg:
        d.rounded_rectangle([56, 56, S - 56, S - 56], radius=200, fill=BG)
    # 三角尖耳（朝上外侧，猫的标志性特征），底部被猫头盖住
    ear(d, [(325, 205), (248, 512), (428, 528)])            # 左耳
    ear(d, [(699, 205), (776, 512), (596, 528)])            # 右耳
    # 内耳小三角
    d.polygon([(340, 300), (300, 430), (372, 450)], fill=INNER)
    d.polygon([(684, 300), (724, 430), (652, 450)], fill=INNER)
    # 猫头大色块（圆润，盖住耳底形成自然衔接）
    d.ellipse([182, 420, 842, 940], fill=CAT, outline=O, width=28)
    # 胡须（左右各 3 根，从脸侧缘向外）
    for (x1, y1, x2, y2) in [
            (240, 600, 96, 560), (220, 680, 76, 680), (250, 752, 110, 802),
            (784, 600, 928, 560), (804, 680, 948, 680), (774, 752, 914, 802)]:
        d.line([(x1, y1), (x2, y2)], fill=O, width=16)
    # 大眼睛（圆润萌感）
    for cx in (398, 626):
        d.ellipse([cx - 60, 576, cx + 60, 696], fill=NOSE)
    # 高光
    for cx in (398, 626):
        d.ellipse([cx - 24, 596, cx - 2, 620], fill=WHITE)
    # 鼻子
    d.ellipse([468, 726, 556, 796], fill=NOSE)
    # 嘴（两条弧线向两边分开）
    d.line([(512, 796), (462, 838)], fill=NOSE, width=18)
    d.line([(512, 796), (562, 838)], fill=NOSE, width=18)
    return im


def fit_to(canvas_size, content, max_d):
    """把 content 缩放到直径 max_d 内并居中到 canvas_size 画布（透明底）。"""
    w, h = content.size
    scale = min(max_d / w, max_d / h)
    nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
    small = content.resize((nw, nh), Image.LANCZOS)
    canvas = Image.new('RGBA', (canvas_size, canvas_size), (0, 0, 0, 0))
    canvas.paste(small, ((canvas_size - nw) // 2, (canvas_size - nh) // 2), small)
    return canvas


def main():
    legacy = draw_cat(with_bg=True)      # 带圆角底
    fg = draw_cat(with_bg=False)          # 纯猫（自适应前景用）

    # legacy ic_launcher / ic_launcher_round
    for dens, px in LEGACY_SIZES.items():
        out = os.path.join(RES, 'mipmap-%s' % dens)
        legacy.resize((px, px), Image.LANCZOS).save(os.path.join(out, 'ic_launcher.png'))
        legacy.resize((px, px), Image.LANCZOS).save(os.path.join(out, 'ic_launcher_round.png'))

    # 自适应前景：内容缩放至直径 285（432 的 66% 安全区）
    fg432 = fit_to(432, fg, 285)
    fg432.save(os.path.join(RES, 'mipmap-anydpi-v26', 'ic_launcher_foreground.png'))
    for dens, px in FG_SIZES.items():
        out = os.path.join(RES, 'mipmap-%s' % dens)
        fg432.resize((px, px), Image.LANCZOS).save(os.path.join(out, 'ic_launcher_foreground.png'))

    # 自适应背景：纯色
    bg = Image.new('RGBA', (432, 432), BG)
    bg.save(os.path.join(RES, 'mipmap-anydpi-v26', 'ic_launcher_background.png'))
    # 同步 colors.xml 的颜色定义（adaptive-icon 引用 @color/ic_launcher_background）
    colors = os.path.join(RES, 'values', 'ic_launcher_background.xml')
    with open(colors, 'w', encoding='utf-8') as f:
        f.write('<?xml version="1.0" encoding="utf-8"?>\n'
                '<resources>\n'
                '    <color name="ic_launcher_background">%s</color>\n'
                '</resources>\n' % BG)

    # 渲染目检页：48px 放大 + 全套尺寸排列
    html = ['<!DOCTYPE html><html><head><meta charset="utf-8"><style>'
            'body{background:#888;font-family:sans-serif;margin:0;padding:20px}'
            '.row{display:flex;gap:24px;align-items:flex-start;flex-wrap:wrap}'
            '.cell{text-align:center;color:#fff;font-size:13px;margin-bottom:20px}'
            'img{border:1px solid #ccc;background:#fff}</style></head><body>']
    html.append('<h3 style="color:#fff">48px 实际尺寸（放大 4 倍预览）</h3><div class="row">')
    leg48 = legacy.resize((48, 48), Image.LANCZOS)
    leg48.save(os.path.join(ROOT, '_icon_48.png'))
    for scale in (1, 2, 4, 8):
        html.append('<div class="cell"><img src="_icon_48.png" width="%d"><br>48px ×%d</div>'
                    % (48 * scale, scale))
    html.append('</div><h3 style="color:#fff">legacy 全套</h3><div class="row">')
    for dens, px in LEGACY_SIZES.items():
        p = os.path.join(ROOT, '_legacy_%s.png' % dens)
        legacy.resize((px, px), Image.LANCZOS).save(p)
        html.append('<div class="cell"><img src="_legacy_%s.png" width="%d"><br>%s %dpx</div>'
                    % (dens, px, dens, px))
    html.append('</div><h3 style="color:#fff">自适应合成（前景+背景）</h3><div class="row">')
    comp = Image.new('RGBA', (432, 432), BG)
    comp.alpha_composite(fg432)
    comp.save(os.path.join(ROOT, '_adaptive.png'))
    html.append('<div class="cell"><img src="_adaptive.png" width="216"><br>adaptive 合成</div>')
    html.append('</div></body></html>')
    with open(os.path.join(ROOT, '_icon_v2_preview.html'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(html))
    print('ALL-ICONS-GENERATED')


if __name__ == '__main__':
    main()