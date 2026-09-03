# -*- coding: utf-8 -*-
"""从原始图标副本 6-phone-cat_icon-icons.com_76682.ico 生成全套安卓图标（v2 高可读版）。

改进点（相对 gen_upstream_icons）：
1. 给小猫加一圈深棕描边（伸边合成，不糊边）——小尺寸下轮廓依然清晰；
2. 底改为更饱满的暖米渐变，与橙猫拉开对比；
3. 自适应图标内容收敛到 66dp 安全区以内（58% 画布），legacy 足幅；
4. 用 1024 主画布逐密度 LANCZOS 下采样，边缘更利。
用法: python tools/gen_app_icons.py
"""
import os

from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, '6-phone-cat_icon-icons.com_76682.ico')
RES = os.path.join(ROOT, 'android', 'app', 'src', 'main', 'res')

MASTER = 1024
OUTLINE = (107, 58, 14, 255)      # 深棕描边
GRAD_TOP = (255, 243, 224)        # 暖米上
GRAD_BOT = (255, 219, 178)        # 暖米下
ADAPTIVE_BG = '#FFE0B3'           # 自适应背景色（放 values 里）


def load_art(size):
    im = Image.open(SRC).convert('RGBA')
    im = im.resize((size, size), Image.LANCZOS)
    # 轻微锐化弥补 128px 源放大后的柔边
    return im.filter(ImageFilter.UnsharpMask(radius=2, percent=70, threshold=2))


def grow_alpha(alpha, pct):
    """把 alpha 向外扩 pct（如 0.055），用于做描边/阴影蒙版。"""
    w, h = alpha.size
    nw, nh = max(1, int(w * (1 + pct))), max(1, int(h * (1 + pct)))
    big = alpha.resize((nw, nh), Image.LANCZOS)
    canvas = Image.new('L', (w, h), 0)
    canvas.paste(big, ((w - nw) // 2, (h - nh) // 2))
    return canvas


def build_art():
    """返回 (小猫+描边) 合成图，透明底，边距极小的正方形。"""
    art = load_art(MASTER)
    alpha = art.getchannel('A')
    # 描边蒙版：alpha 外扩 5.5%
    rim_alpha = grow_alpha(alpha, 0.055)
    # 稍作羽化让描边外缘自然
    rim_alpha = rim_alpha.filter(ImageFilter.GaussianBlur(1.2))
    rim = Image.new('RGBA', (MASTER, MASTER), (0, 0, 0, 0))
    rim.putalpha(rim_alpha)
    solid = Image.new('RGBA', (MASTER, MASTER), OUTLINE)
    rim = Image.composite(solid, rim, rim_alpha)  # 给描边层填色（保留羽化半透明）
    # 描边在下，猫在上
    out = Image.new('RGBA', (MASTER, MASTER), (0, 0, 0, 0))
    out.alpha_composite(rim)
    out.alpha_composite(art)
    # 裁掉因描边略微外扩而产生的透明边距，保持内容贴边
    bbox = out.getbbox()
    if bbox:
        out = out.crop(bbox)
    return out


def vgrad(size, top, bottom):
    """竖渐变底（整幅不透明）。"""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    big = Image.new('RGBA', (size, size * 4), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    for y in range(size * 4):
        t = y / (size * 4)
        c = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)) + (255,)
        d.line([(0, y), (size, y)], fill=c)
    img.alpha_composite(big.resize((size, size), Image.LANCZOS))
    return img


def rounded_mask(size, radius_ratio):
    m = Image.new('L', (size, size), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size - 1, size - 1],
                                        radius=int(size * radius_ratio), fill=255)
    return m


def circle_mask(size):
    m = Image.new('L', (size, size), 0)
    ImageDraw.Draw(m).ellipse([0, 0, size - 1, size - 1], fill=255)
    return m


def paste_scaled(canvas, art, scale):
    cw, ch = canvas.size
    w = max(1, int(cw * scale))
    a = art.resize((w, w), Image.LANCZOS)
    x, y = (cw - w) // 2, (ch - w) // 2
    canvas.alpha_composite(a, (x, y))


def masked_full(img, mask):
    """把整幅 img 按 mask 裁切后贴到透明画布上（用于圆角/圆形底）。"""
    out = Image.new('RGBA', img.size, (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return out


def main():
    art = build_art()
    legacy = {
        'mipmap-mdpi': 48, 'mipmap-hdpi': 72, 'mipmap-xhdpi': 96,
        'mipmap-xxhdpi': 144, 'mipmap-xxxhdpi': 192,
    }
    for d, size in legacy.items():
        folder = os.path.join(RES, d)
        # legacy 方形：圆角渐变底（圆角 22% 透明角由 Launcher 显示） + 小猫 86%
        bg = vgrad(size, GRAD_TOP, GRAD_BOT)
        icon = masked_full(bg, rounded_mask(size, 0.22))
        paste_scaled(icon, art, 0.86)
        icon.save(os.path.join(folder, 'ic_launcher.png'))
        # legacy round：圆形底 + 小猫 82%
        rnd = masked_full(bg, circle_mask(size))
        paste_scaled(rnd, art, 0.82)
        rnd.save(os.path.join(folder, 'ic_launcher_round.png'))
        # 密度级自适应前景（备用，主用 anydpi-v26）
        fg = Image.new('RGBA', (size * 2, size * 2), (0, 0, 0, 0))
        paste_scaled(fg, art, 0.58)
        fg.save(os.path.join(folder, 'ic_launcher_foreground.png'))
        print('generated', d, size)

    # anydpi-v26：自适应前景 432（108dp @4x），内容收敛在 66dp 安全区内
    v26 = os.path.join(RES, 'mipmap-anydpi-v26')
    fg432 = Image.new('RGBA', (432, 432), (0, 0, 0, 0))
    paste_scaled(fg432, art, 0.58)
    fg432.save(os.path.join(v26, 'ic_launcher_foreground.png'))
    bg432 = vgrad(432, GRAD_TOP, GRAD_BOT)
    bg432.save(os.path.join(v26, 'ic_launcher_background.png'))
    print('generated anydpi-v26 (432)')

    # 自适应背景色（values）
    col_path = os.path.join(RES, 'values', 'ic_launcher_background.xml')
    with open(col_path, 'w', encoding='utf-8') as f:
        f.write('<?xml version="1.0" encoding="utf-8"?>\n'
                '<resources>\n    <color name="ic_launcher_background">%s</color>\n</resources>\n'
                % ADAPTIVE_BG)
    print('generated color', ADAPTIVE_BG)


if __name__ == '__main__':
    main()
