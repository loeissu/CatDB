# -*- coding: utf-8 -*-
"""从上游原始项目图标 6-phone-cat_icon-icons.com_76682.ico 生成：
- Android legacy launcher png（米色圆角底 + 居中猫）+ round 版本
- Android adaptive icon foreground（透明底，内容居中 66% 安全区）
- Windows EXE 多尺寸 .ico
用法: python tools/gen_upstream_icons.py
"""
import io
import os

from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, '6-phone-cat_icon-icons.com_76682.ico')
BG_COLOR = '#F6E9D8'  # 自适应图标背景（浅米色，与 App 主页一致）


def load_source(size=None):
    """读取源图标 128px 帧。若图标含 alpha 且内容有白底则透明化处理由调用方决定。"""
    im = Image.open(SRC)
    im.seek(0)
    im = im.convert('RGBA')
    if size and im.size[0] != size:
        im = im.resize((size, size), Image.LANCZOS)
    return im


def paste_center(canvas, art, scale):
    """把 art 按 scale(0~1) 等比缩小后居中贴到 canvas。"""
    cw, ch = canvas.size
    w, h = int(cw * scale), int(ch * scale)
    art = art.resize((w, h), Image.LANCZOS)
    canvas.alpha_composite(art, ((cw - w) // 2, (ch - h) // 2))


def rounded_bg(size, radius_ratio=0.22, gradient=True):
    """米色渐变圆角底。返回 (img, mask)"""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    if gradient:
        top = (255, 247, 235)
        bottom = (255, 226, 199)
        grad = Image.new('RGBA', (size, size * 4))
        for y in range(size * 4):
            t = y / (size * 4)
            col = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)) + (255,)
            ImageDraw.Draw(grad).line([(0, y), (size, y)], fill=col)
        grad = grad.resize((size, size), Image.LANCZOS)
        img.alpha_composite(grad)
    else:
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, size, size], fill=BG_COLOR)
    mask = Image.new('L', (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=int(size * radius_ratio), fill=255)
    out = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return out


def circle_bg(size):
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    m = Image.new('RGBA', (size * 4, size * 4), (0, 0, 0, 0))
    ImageDraw.Draw(m).ellipse([0, 0, size * 4, size * 4], fill=BG_COLOR)
    m = m.resize((size, size), Image.LANCZOS)
    img.alpha_composite(m)
    return img


def main():
    if not os.path.exists(SRC):
        raise SystemExit('缺少源图标: %s' % SRC)
    res = os.path.join(ROOT, 'android', 'app', 'src', 'main', 'res')
    src_art = load_source(512).crop((0, 0, 512, 512))

    legacy = {
        'mipmap-mdpi': 48, 'mipmap-hdpi': 72, 'mipmap-xhdpi': 96,
        'mipmap-xxhdpi': 144, 'mipmap-xxxhdpi': 192,
    }
    for d, size in legacy.items():
        # 圆角渐变米色底 + 居中猫（占比 90%，猫最大可见）
        canvas = rounded_bg(size)
        paste_center(canvas, src_art, 0.9)
        canvas.save(os.path.join(res, d, 'ic_launcher.png'))

        rnd = circle_bg(size)
        paste_center(rnd, src_art, 0.9)
        rnd.save(os.path.join(res, d, 'ic_launcher_round.png'))

        # adaptive foreground：透明底、内容居中约 66%（Android 安全区 66/108dp）
        fg = Image.new('RGBA', (size * 2, size * 2), (0, 0, 0, 0))
        paste_center(fg, src_art, 0.66)
        fg.save(os.path.join(res, d, 'ic_launcher_foreground.png'))
        print('generated', d, size)

    # 自适应背景色
    bg = os.path.join(res, 'values', 'ic_launcher_background.xml')
    with open(bg, 'w', encoding='utf-8') as f:
        f.write('<?xml version="1.0" encoding="utf-8"?>\n'
                '<resources>\n    <color name="ic_launcher_background">%s</color>\n</resources>\n' % BG_COLOR)

    # anydpi-v26 备用 432px
    v26 = os.path.join(res, 'mipmap-anydpi-v26')
    bg432 = rounded_bg(432)
    paste_center(bg432, src_art, 0.9)
    bg432.save(os.path.join(v26, 'ic_launcher_background.png'))
    fg432 = Image.new('RGBA', (432, 432), (0, 0, 0, 0))
    paste_center(fg432, src_art, 0.66)
    fg432.save(os.path.join(v26, 'ic_launcher_foreground.png'))
    print('generated anydpi-v26')

    # Windows EXE .ico（16..256，透明底猫；小尺寸保持清晰）
    ico_sizes = [16, 24, 32, 48, 64, 128, 256]
    ico_path = os.path.join(ROOT, 'cat_icon.ico')
    frames = [load_source(s if s <= 128 else 256).resize((s, s), Image.LANCZOS) for s in ico_sizes]
    frames[-1].save(ico_path, format='ICO', sizes=[(s, s) for s in ico_sizes], append_images=frames[:-1])
    print('generated', ico_path)


if __name__ == '__main__':
    main()
