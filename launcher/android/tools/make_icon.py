"""Рисует иконку ONIKS RP во всех плотностях: res/mipmap-*/ic_launcher.png и icon-512.png.
Огранённый чёрный камень (оникс) с оранжевыми гранями на графитовом фоне."""
import math
import os

from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIZES = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}
ORANGE = (255, 138, 61)


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(len(a)))


def draw(n):
    s = 4 * n  # рисуем крупно и уменьшаем — так края гладкие
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    # фон: вертикальный градиент графита
    bg = Image.new("RGBA", (s, s))
    bd = ImageDraw.Draw(bg)
    for y in range(s):
        bd.line([(0, y), (s, y)], fill=lerp((34, 38, 48, 255), (12, 13, 17, 255), y / s))
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, s - 1, s - 1], s * 0.22, fill=255)
    im.paste(bg, (0, 0), mask)

    # мягкое оранжевое свечение за камнем
    glow = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([s * 0.2, s * 0.24, s * 0.8, s * 0.84], fill=ORANGE + (120,))
    glow = glow.filter(ImageFilter.GaussianBlur(s * 0.08))
    im = Image.alpha_composite(im, glow)

    # огранённый камень: верхняя площадка, корона и павильон
    cx, top, w = s / 2, s * 0.24, s * 0.56
    girdle = s * 0.42
    tip = s * 0.84
    table = w * 0.46
    pts_crown = [(cx - w / 2, girdle), (cx - table / 2, top), (cx + table / 2, top), (cx + w / 2, girdle)]
    d = ImageDraw.Draw(im)
    # павильон (нижняя часть) — несколько граней разной темноты
    facets = 6
    for i in range(facets):
        x0 = cx - w / 2 + w * i / facets
        x1 = cx - w / 2 + w * (i + 1) / facets
        shade = 18 + int(26 * (0.5 + 0.5 * math.cos((i + 0.5) / facets * math.pi * 1.2)))
        d.polygon([(x0, girdle), (x1, girdle), (cx, tip)], fill=(shade, shade, shade + 6, 255))
    # корона
    d.polygon(pts_crown, fill=(44, 46, 56, 255))
    for i in range(4):
        x0 = cx - w / 2 + w * i / 4
        x1 = cx - w / 2 + w * (i + 1) / 4
        tx0 = cx - table / 2 + table * i / 4
        tx1 = cx - table / 2 + table * (i + 1) / 4
        shade = 40 + 14 * (i % 2)
        d.polygon([(x0, girdle), (x1, girdle), (tx1, top), (tx0, top)], fill=(shade, shade, shade + 8, 255))
    # оранжевые рёбра
    lw = max(2, int(s * 0.012))
    outline = [(cx - w / 2, girdle), (cx - table / 2, top), (cx + table / 2, top), (cx + w / 2, girdle), (cx, tip)]
    d.line(outline + [outline[0]], fill=ORANGE + (255,), width=lw, joint="curve")
    d.line([(cx - w / 2, girdle), (cx + w / 2, girdle)], fill=ORANGE + (255,), width=lw)
    for i in range(1, facets):
        x = cx - w / 2 + w * i / facets
        d.line([(x, girdle), (cx, tip)], fill=ORANGE + (150,), width=max(1, lw // 2))
    # блик
    d.polygon([(cx - table / 2 + s * 0.02, top + s * 0.015), (cx - table * 0.05, top + s * 0.015), (cx - w * 0.28, girdle - s * 0.02)],
              fill=(255, 255, 255, 70))
    im.putalpha(Image.composite(im.getchannel("A"), Image.new("L", (s, s), 0), mask))
    return im.resize((n, n), Image.LANCZOS)


for name, n in SIZES.items():
    out = os.path.join(ROOT, "res", f"mipmap-{name}")
    os.makedirs(out, exist_ok=True)
    draw(n).save(os.path.join(out, "ic_launcher.png"))
draw(512).save(os.path.join(ROOT, "icon-512.png"))
print("ok")
