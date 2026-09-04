# -*- coding: utf-8 -*-
"""
「Typing」文字版安卓启动器图标：
- legacy：橙色渐变圆角底 + 白色粗体 "Typing"（带柔和阴影），深/浅壁纸均醒目
- adaptive：前景=白色文字（66% 安全区内），背景=品牌橙纯色
- 用户后续会重新设计图标，此版本为占位文字方案
"""
import os
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(ROOT, 'android', 'app', 'src', 'main', 'res')

S = 1024
WORD = 'Typing'
FONT_PATH = 'C:/Windows/Fonts/arialbd.ttf'
TOP = '#FFB74D'      # 渐变上（亮橙）
BOT = '#F59E42'      # 渐变下（橙）
BG_SOLID = '#F59E42'  # adaptive 背景纯色
SHADOW = (60, 30, 10, 110)

LEGACY_SIZES = {'mdpi': 48, 'hdpi': 72, 'xhdpi': 96, 'xxhdpi': 144, 'xxxhdpi': 192}
FG_SIZES = {'mdpi': 108, 'hdpi': 162, 'xhdpi': 216, 'xxhdpi': 324, 'xxxhdpi': 432}


def vertical_gradient(w, h, top, bottom):
    base = Image.new('RGBA', (w, h))
    for y in range(h):
        t = y / max(1, h - 1)
        row = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)) + (255,)
        ImageDraw.Draw(base).line([(0, y), (w, y)], fill=row)
    return base


def text_layer(text, font_path, size, max_w):
    """渲染带阴影的白色文字到透明层，返回 (layer, bbox)。"""
    font = ImageFont.truetype(font_path, size)
    probe = ImageDraw.Draw(Image.new('RGBA', (8, 8)))
    left, top, right, bottom = probe.textbbox((0, 0), text, font=font)
    tw, th = right - left, bottom - top
    scale = min(1.0, max_w / tw)          # 超宽则缩小
    if scale < 1.0:
        size = max(1, int(size * scale))
        font = ImageFont.truetype(font_path, size)
        left, top, right, bottom = probe.textbbox((0, 0), text, font=font)
        tw, th = right - left, bottom - top
    pad = 40
    layer = Image.new('RGBA', (tw + pad * 2, th + pad * 2 + 30), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    x, y = pad - left, pad - top
    d.text((x, y + 22), text, font=font, fill=SHADOW)   # 阴影下移
    d.text((x, y), text, font=font, fill=(255, 255, 255, 255))
    return layer, (tw + pad * 2, th + pad * 2 + 30)


def legacy_master():
    """1024 圆角渐变底 + 文字（legacy 图标整图）。"""
    grad = vertical_gradient(S, S, tuple(int(TOP[i:i + 2], 16) for i in (1, 3, 5)),
                             tuple(int(BOT[i:i + 2], 16) for i in (1, 3, 5)))
    mask = Image.new('L', (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([48, 48, S - 48, S - 48], radius=210, fill=255)
    base = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    base.paste(grad, (0, 0), mask)
    layer, _ = text_layer(WORD, FONT_PATH, 400, 800)
    lw, lh = layer.size
    base.alpha_composite(layer, ((S - lw) // 2, (S - lh) // 2 - 20))
    return base


def fg_master():
    """自适应前景：纯文字，整体限入 66% 安全区。"""
    layer, _ = text_layer(WORD, FONT_PATH, 400, 250)
    lw, lh = layer.size
    canvas = Image.new('RGBA', (432, 432), (0, 0, 0, 0))
    canvas.alpha_composite(layer, ((432 - lw) // 2, (432 - lh) // 2))
    return canvas


def main():
    leg = legacy_master()
    fg = fg_master()

    for dens, px in LEGACY_SIZES.items():
        out = os.path.join(RES, 'mipmap-%s' % dens)
        leg.resize((px, px), Image.LANCZOS).save(os.path.join(out, 'ic_launcher.png'))
        leg.resize((px, px), Image.LANCZOS).save(os.path.join(out, 'ic_launcher_round.png'))

    fg.save(os.path.join(RES, 'mipmap-anydpi-v26', 'ic_launcher_foreground.png'))
    for dens, px in FG_SIZES.items():
        out = os.path.join(RES, 'mipmap-%s' % dens)
        fg.resize((px, px), Image.LANCZOS).save(os.path.join(out, 'ic_launcher_foreground.png'))

    bg = Image.new('RGBA', (432, 432), BG_SOLID)
    bg.save(os.path.join(RES, 'mipmap-anydpi-v26', 'ic_launcher_background.png'))
    colors = os.path.join(RES, 'values', 'ic_launcher_background.xml')
    with open(colors, 'w', encoding='utf-8') as f:
        f.write('<?xml version="1.0" encoding="utf-8"?>\n'
                '<resources>\n'
                '    <color name="ic_launcher_background">%s</color>\n'
                '</resources>\n' % BG_SOLID)

    # 目检素材
    leg.resize((192, 192), Image.LANCZOS).save(os.path.join(ROOT, '_typing_192.png'))
    leg.resize((48, 48), Image.LANCZOS).save(os.path.join(ROOT, '_typing_48.png'))
    comp = Image.new('RGBA', (432, 432), BG_SOLID)
    comp.alpha_composite(fg)
    comp.save(os.path.join(ROOT, '_typing_adaptive.png'))
    print('TYPING-ICONS-GENERATED')


if __name__ == '__main__':
    main()