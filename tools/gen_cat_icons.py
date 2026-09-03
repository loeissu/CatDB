# -*- coding: utf-8 -*-
"""生成豆包喵喵小猫图标（与主页小猫同款画风）：
- Android legacy launcher png (mipmap-*) + round 版本
- Android adaptive icon foreground（透明底、内容居中安全区）
- Windows EXE .ico
用法: python tools/gen_cat_icons.py
"""
import math
import os

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CAT = (93, 64, 55)        # #5D4037 深棕（与主页小猫一致）
INNER = (255, 171, 145)   # 耳内粉色 #FFAB91
NOSE = (255, 138, 101)    # 鼻子 #FF8A65
WHISK = (255, 255, 255)
BG_TOP = (255, 247, 235)
BG_BOT = (255, 226, 199)
BG_COLOR = '#F6E9D8'      # 自适应图标背景（浅米色）


def draw_cat_art(size, bg_round=False, adaptive=False):
    """在 size×size RGBA 画布上绘制小猫。adaptive=True 时透明底（前景）。"""
    S = float(size)
    if adaptive:
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    elif bg_round:
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        # 圆形米色底
        m = Image.new('RGBA', (size * 4, size * 4), (0, 0, 0, 0))
        md = ImageDraw.Draw(m)
        md.ellipse([0, 0, size * 4, size * 4], fill=BG_TOP)
        m = m.resize((size, size), Image.LANCZOS)
        img = m
    else:
        # 圆角方形渐变底（模拟主页米色纸面）
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        grad = Image.new('RGBA', (size, size))
        gd = ImageDraw.Draw(grad)
        for y in range(size):
            t = y / max(1, size - 1)
            c = tuple(int(BG_TOP[i] + (BG_BOT[i] - BG_TOP[i]) * t) for i in range(3))
            gd.line([(0, y), (size, y)], fill=c + (255,))
        mask = Image.new('L', (size * 4, size * 4), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, size * 4, size * 4], radius=int(size * 4 * 0.22), fill=255)
        mask = mask.resize((size, size), Image.LANCZOS)
        img.paste(grad, (0, 0), mask)
        img = grad
        img.putalpha(mask)

    d = ImageDraw.Draw(img)

    def p(x, y):
        return (x * S, y * S)

    # 画布归一化布局
    hx, hy = 0.5, 0.52            # 头中心
    hw = 0.30                     # 半宽
    hh = 0.21                     # 半高（扁圆）
    ear_w = 0.145
    ear_h = 0.20
    # 耳朵
    for sgn in (-1, 1):
        ex = hx + sgn * (hw - ear_w * 0.28)
        top = hy - hh - ear_h * 0.62
        base = hy - hh + 0.035
        d.polygon([p(ex - sgn * ear_w, base),
                   p(ex + sgn * ear_w * 0.35, base),
                   p(ex + sgn * 0.06, top)], fill=CAT)
        # 耳内粉
        ix = ex + sgn * 0.02
        d.polygon([p(ix - sgn * ear_w * 0.5, base - 0.012),
                   p(ix + sgn * ear_w * 0.22, base - 0.012),
                   p(ix + sgn * 0.02, top + 0.055)], fill=INNER)
    # 头（椭圆）
    d.ellipse([p(hx - hw, hy - hh), p(hx + hw, hy + hh)], fill=CAT)
    # 眼睛（两条温柔弧线 → 圆点简化为适合小尺寸）
    er = 0.022
    for sgn in (-1, 1):
        ex = hx + sgn * (hw * 0.42)
        ey = hy - hh * 0.18
        d.ellipse([p(ex - er, ey - er * 1.25), p(ex + er, ey + er * 1.25)], fill=(255, 255, 255, 255))
        # 瞳孔
        d.ellipse([p(ex - er * 0.45, ey - er * 0.5), p(ex + er * 0.45, ey + er * 0.5)], fill=CAT)
    # 鼻子（小三角圆）
    nr = hh * 0.10
    d.polygon([p(hx, hy + nr * 0.15), p(hx - nr * 1.15, hy - nr * 0.95), p(hx + nr * 1.15, hy - nr * 0.95)],
              fill=NOSE)
    d.ellipse([p(hx - nr * 0.7, hy - nr * 1.25), p(hx + nr * 0.7, hy - nr * 0.05)], fill=NOSE)
    # 嘴巴：两个小弧
    mx, my = hx, hy + nr * 0.2
    d.arc([p(mx - hw * 0.14, my), p(mx, my + hh * 0.22)], 180, 360, fill=(240, 230, 220, 255), width=max(1, int(S * 0.008)))
    d.arc([p(mx, my), p(mx + hw * 0.14, my + hh * 0.22)], 180, 360, fill=(240, 230, 220, 255), width=max(1, int(S * 0.008)))
    # 胡须
    ww = int(S * 0.012)
    yy = [hy - hh * 0.05, hy + hh * 0.12]
    for y0 in yy:
        d.line([p(hx - hw * 0.98, y0 - 0.02), p(hx - hw * 1.32, y0 - 0.05)], fill=WHISK, width=ww)
        d.line([p(hx - hw * 0.98, y0 + 0.05), p(hx - hw * 1.30, y0 + 0.09)], fill=WHISK, width=ww)
        d.line([p(hx + hw * 0.98, y0 - 0.02), p(hx + hw * 1.32, y0 - 0.05)], fill=WHISK, width=ww)
        d.line([p(hx + hw * 0.98, y0 + 0.05), p(hx + hw * 1.30, y0 + 0.09)], fill=WHISK, width=ww)
    return img


def make_adaptive_foreground(size):
    """透明画布，内容置于中央 66% 安全区内，适配图标所需内缩。"""
    S = float(size)
    canvas = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    art = draw_cat_art(int(S * 0.72), bg_round=False, adaptive=True)
    canvas.paste(art, (int(S * 0.14), int(S * 0.14)), art)
    return canvas


def main():
    res = os.path.join(ROOT, 'android', 'app', 'src', 'main', 'res')
    legacy = {
        'mipmap-mdpi': 48, 'mipmap-hdpi': 72, 'mipmap-xhdpi': 96,
        'mipmap-xxhdpi': 144, 'mipmap-xxxhdpi': 192,
    }
    for d, size in legacy.items():
        art = draw_cat_art(size)
        art.save(os.path.join(res, d, 'ic_launcher.png'))
        rnd = draw_cat_art(size, bg_round=True)
        rnd.save(os.path.join(res, d, 'ic_launcher_round.png'))
        fg = make_adaptive_foreground(size * 2)  # 前景按 2x 存储，供 v26 缩放
        fg.save(os.path.join(res, d, 'ic_launcher_foreground.png'))
        print('generated', d, size)

    # 自适应背景色（浅米色）与旧前景 mipmap-anydpi-v26 备用文件
    bg = os.path.join(res, 'values', 'ic_launcher_background.xml')
    with open(bg, 'w', encoding='utf-8') as f:
        f.write('<?xml version="1.0" encoding="utf-8"?>\n'
                '<resources>\n    <color name="ic_launcher_background">%s</color>\n</resources>\n' % BG_COLOR)

    # EXE 图标（透明圆角方）
    ico_sizes = [16, 24, 32, 48, 64, 128, 256]
    ico_path = os.path.join(ROOT, 'cat_icon.ico')
    imgs = []
    for s in ico_sizes:
        art = draw_cat_art(s, bg_round=False)
        if s >= 48:
            art = draw_cat_art(s)  # legacy 带米色底
        imgs.append(art)
    imgs[-1].save(ico_path, format='ICO', sizes=[(s, s) for s in ico_sizes],
                  append_images=imgs[:-1])
    print('generated', ico_path)


if __name__ == '__main__':
    main()
