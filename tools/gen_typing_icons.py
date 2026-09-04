# -*- coding: utf-8 -*-
"""
「Typing」文字版安卓启动器图标 —— 正式设计稿（v2.2.11，方案 B 奶油底深棕字）

设计要点（与桌面端品牌一致，非占位）：
- 底色：米白奶油渐变（上 #FFFFFF → 中 #FFF9F0 → 下 #F7EAD8），与 Windows 桌面端
  主界面/网页底色同一体系；顶部主光源柔光 + 底部暖色暗角 + 细描边，营造纸感光影
- 主体：深棕(#6D4A33→#4E3220 纵向渐变)粗体「Typing」，下方一条橙色手绘笔触点缀
  （呼应 Windows 猫图标里的橙色），整体呈"白纸 + 深棕字 + 橙笔"的排版意象
- 字形：软投影（深棕 alpha 高斯模糊）+ 垂直渐变填充，48px 依然清晰可辨
- legacy：1024 圆角奶油底整图（legacy + round 同一母版，legacy 形状由启动器掩膜裁切）
- adaptive：前景=仅文字组（66% 安全区内），背景=纯奶油色
"""
import os
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(ROOT, 'android', 'app', 'src', 'main', 'res')

WORD = 'Typing'
FONT_PATH = 'C:/Windows/Fonts/arialbd.ttf'

# ---- 配色（均为设计定稿色值）----
BG_TOP = (0xFF, 0xFF, 0xFF)     # 渐变顶（受光）
BG_MID = (0xFF, 0xF9, 0xF0)     # 渐变中（奶油主色）
BG_BOT = (0xF7, 0xEA, 0xD8)     # 渐变底（暖暗角起始）
BG_SOLID = '#FFF9F0'            # adaptive 背景纯色（= BG_MID）
INK_TOP = (0x6D, 0x4A, 0x33)    # 字色上（浅棕）
INK_BOT = (0x4E, 0x32, 0x20)    # 字色下（深棕）
SHADOW_RGB = (90, 60, 40)       # 字投影
VIGNETTE = (150, 108, 70)       # 底部暖暗角
RING = (196, 156, 116)          # 细描边
BRUSH = (0xFF, 0x8A, 0x3D)      # 橙色笔触（品牌橙）

LEGACY_SIZES = {'mdpi': 48, 'hdpi': 72, 'xhdpi': 96, 'xxhdpi': 144, 'xxxhdpi': 192}
FG_SIZES = {'mdpi': 108, 'hdpi': 162, 'xhdpi': 216, 'xxhdpi': 324, 'xxxhdpi': 432}


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def hex_rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def vertical_gradient(w, h, stops):
    """multi-stop vertical gradient rows, stops = [(pos0..1, rgb)]"""
    img = Image.new('RGBA', (w, h))
    px = img.load()
    for y in range(h):
        t = y / max(1, h - 1)
        for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
            if p0 <= t <= p1:
                col = lerp(c0, c1, 0 if p1 == p0 else (t - p0) / (p1 - p0))
                break
        else:
            col = stops[-1][1]
        for x in range(w):
            px[x, y] = col + (255,)
    return img


def rounded_rect_layer(size, radius, margin, fill):
    layer = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle([margin, margin, size - 1 - margin, size - 1 - margin],
                        radius=radius, fill=fill)
    return layer


def radial_glow(size, box, color, blur):
    glow = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse(box, fill=color)
    return glow.filter(ImageFilter.GaussianBlur(blur))


def text_layer(text, font_path, target_w, max_h):
    """白字透明层，宽度适配 target_w，返回 (layer, w, h)"""
    probe = ImageDraw.Draw(Image.new('RGBA', (8, 8)))
    # 先粗估字号（Arial Bold 400px ≈ 宽 755/1024 比例）
    size = max(12, int(target_w * 400 / 760))
    while True:
        font = ImageFont.truetype(font_path, size)
        l, t, r, b = probe.textbbox((0, 0), text, font=font)
        tw, th = r - l, b - t
        if tw <= target_w or size <= 12:
            break
        size = int(size * target_w / max(1, tw))
    pad = 40
    layer = Image.new('RGBA', (tw + pad * 2, th + pad * 2), (0, 0, 0, 0))
    ImageDraw.Draw(layer).text((pad - l, pad - t), text, font=font,
                               fill=(255, 255, 255, 255))
    return layer, tw + pad * 2, th + pad * 2


def tint_by_alpha(layer, top, bottom):
    """以 layer 的 alpha 为蒙版填充纵向渐变（3 元组颜色）"""
    a = layer.split()[3]
    grad = Image.new('RGBA', layer.size)
    d = ImageDraw.Draw(grad)
    h = layer.size[1]
    for y in range(h):
        t = y / max(1, h - 1)
        d.line([(0, y), (layer.size[0], y)], fill=lerp(top, bottom, t) + (255,))
    grad.putalpha(a)
    return grad


def blur_copy(layer, rgb, dx, dy, blur):
    solid = Image.new('RGBA', layer.size, rgb + (255,))
    solid.putalpha(layer.split()[3])
    if blur > 0:
        solid = solid.filter(ImageFilter.GaussianBlur(blur))
    out = Image.new('RGBA', layer.size, (0, 0, 0, 0))
    out.alpha_composite(solid, (dx, dy))
    return out


def brush_stroke(draw, x0, x1, y, width, color):
    """手绘质感橙色笔触：沿横向一串椭圆+连线"""
    steps = max(6, int((x1 - x0) / 22))
    prev = None
    for i in range(steps + 1):
        t = i / steps
        x = x0 + (x1 - x0) * t
        wob = ((i * 7) % 5 - 2) * (1 - abs(t - 0.5) * 1.6)  # 轻微抖动
        r = max(2, width * (0.72 + 0.28 * abs(t - 0.5) * 2))
        draw.ellipse([x - r, y - r + wob, x + r, y + r + wob], fill=color)
        if prev:
            draw.line([prev, (x, y + wob)], fill=color, width=max(2, int(width * 0.75)))
        prev = (x, y + wob)


def wordmark(canvas_size, letters_w_frac, blur_scale=1.0):
    """
    在透明画布上以 (letters+笔触) 整体居中排版，返回画布。
    letters_w_frac：文字宽度占画布比例（legacy≈0.66 主视觉；adaptive≈0.52 安全区内）
    """
    C = canvas_size
    letters_target = int(C * letters_w_frac)
    layer, lw, lh = text_layer(WORD, FONT_PATH, letters_target, C)
    # 字色纵向渐变
    ink = tint_by_alpha(layer, INK_TOP, INK_BOT)
    # 软投影（深棕，微微下移）
    sh = blur_copy(layer, SHADOW_RGB, 0, int(0.018 * C * blur_scale),
                   max(1, int(0.020 * C * blur_scale)))
    # 笔触：宽约为字宽的 0.62，位于字底下方
    stroke_w = max(60, int(lw * 0.62))
    stroke_y_abs = int(0.062 * C)  # 与字的竖直间距（随画布缩放）

    canvas = Image.new('RGBA', (C, C), (0, 0, 0, 0))
    # 计算整体包围盒并垂直居中：上=字顶, 下=笔触底
    sh_top = int(0.018 * C * blur_scale)
    top = (C - lh) // 2
    bottom = top + lh - 1 + stroke_y_abs
    box_h = bottom - top + 1
    # 视觉重心略上移（顶部留白略大于底部投影留白）
    cy0 = (C - box_h) // 2
    ly = cy0 - sh_top
    canvas.alpha_composite(sh, ((C - lw) // 2, ly))
    canvas.alpha_composite(ink, ((C - lw) // 2, ly))
    # 笔触
    s_cx = C // 2
    s_y = ly + lh - 1 + stroke_y_abs - max(1, int(0.008 * C * blur_scale))
    brush = Image.new('RGBA', (C, C), (0, 0, 0, 0))
    brush_stroke(ImageDraw.Draw(brush), s_cx - stroke_w // 2, s_cx + stroke_w // 2,
                 s_y, max(4, int(0.020 * C * blur_scale)), BRUSH + (255,))
    canvas.alpha_composite(brush)
    return canvas


def legacy_master():
    """1024 圆角奶油底 + 顶部柔光 + 底部暖暗角 + 细描边 + 居中字组"""
    S = 1024
    M = 46          # 四边留白（圆角底边距）
    R = 208         # 圆角半径
    base = rounded_rect_layer(S, R, M, (255, 255, 255, 255))
    # 底色纵向渐变（白→奶油→暖底）
    grad = vertical_gradient(S, S, [(0.0, BG_TOP), (0.5, BG_MID), (1.0, BG_BOT)])
    base.paste(grad, (0, 0), base.split()[3])
    # 顶部主光源柔光
    base.alpha_composite(radial_glow(S, [-0.1 * S, -0.45 * S, 1.1 * S, 0.55 * S],
                                     (255, 255, 255, 120), int(0.10 * S)))
    # 底部暖色暗角
    base.alpha_composite(radial_glow(S, [-0.3 * S, 0.52 * S, 1.3 * S, 1.6 * S],
                                     VIGNETTE + (95,), int(0.12 * S)))
    # 细描边（纸感边框，低透明度）
    ring = ImageDraw.Draw(base)
    ring.rounded_rectangle([M + 6, M + 6, S - 1 - M - 6, S - 1 - M - 6],
                           radius=R - 6, outline=RING + (70,), width=3)
    # 字组（视觉居中：整体包围盒中心≈画布中心，避免笔触使整体偏低）
    wm = wordmark(S, 0.66, blur_scale=1.0)
    # wordmark() 已将内容整体居中
    base.alpha_composite(wm)
    return base


def fg_master():
    """自适应前景：仅字组（含投影与笔触），整体纳入 66% 安全区（圆直径≈0.61C）"""
    C = 432
    return wordmark(C, 0.52, blur_scale=0.42)


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

    bg = Image.new('RGBA', (432, 432), hex_rgb(BG_SOLID) + (255,))
    bg.save(os.path.join(RES, 'mipmap-anydpi-v26', 'ic_launcher_background.png'))
    colors = os.path.join(RES, 'values', 'ic_launcher_background.xml')
    with open(colors, 'w', encoding='utf-8') as f:
        f.write('<?xml version="1.0" encoding="utf-8"?>\n'
                '<resources>\n'
                '    <color name="ic_launcher_background">%s</color>\n'
                '</resources>\n' % BG_SOLID)

    # 目检素材（build/ 已 gitignore，不污染仓库）
    prev = os.path.join(ROOT, 'build', 'icon_preview')
    os.makedirs(prev, exist_ok=True)
    leg.resize((192, 192), Image.LANCZOS).save(os.path.join(prev, '_typing_192.png'))
    leg.resize((48, 48), Image.LANCZOS).save(os.path.join(prev, '_typing_48.png'))
    comp = Image.new('RGBA', (432, 432), hex_rgb(BG_SOLID) + (255,))
    comp.alpha_composite(fg)
    comp.save(os.path.join(prev, '_typing_adaptive.png'))
    print('TYPING-ICONS-GENERATED ->', prev)


if __name__ == '__main__':
    main()
