"""Рисует фирменный баннер для шапки бота (banner.png) из BRAND и TAGLINE."""

import math
import os
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont

import config

W, H = 1280, 640
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "banner.png")

FONT_DIRS = ["/usr/share/fonts/truetype", "/system/fonts",
             "/data/data/com.termux/files/usr/share/fonts", HERE]


def find_font(names: list[str], size: int) -> ImageFont.FreeTypeFont:
    for n in names:  # сначала ищем самый желанный шрифт во всех папках
        for d in FONT_DIRS:
            for root, _, files in os.walk(d):
                if n in files:
                    return ImageFont.truetype(os.path.join(root, n), size)
    return ImageFont.load_default(size)


def glow(img: Image.Image, cx: float, cy: float, rx: float, ry: float,
         color: tuple, alpha: int, blur: int) -> None:
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=color + (alpha,))
    img.alpha_composite(layer.filter(ImageFilter.GaussianBlur(blur)))


def shield(size: int) -> Image.Image:
    """Щит с градиентом и галочкой."""
    s = size
    pts = [(s * .5, s * .04), (s * .92, s * .2), (s * .88, s * .58),
           (s * .5, s * .96), (s * .12, s * .58), (s * .08, s * .2)]
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).polygon(pts, fill=255)
    grad = Image.new("RGBA", (s, s))
    gd = ImageDraw.Draw(grad)
    for y in range(s):
        t = y / s
        c = (int(41 + (124 - 41) * t), int(182 + (77 - 182) * t), int(246 + (255 - 246) * t), 255)
        gd.line([(0, y), (s, y)], fill=c)
    out = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    out.paste(grad, (0, 0), mask)
    # мягкий блик по левой половине щита
    hl = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ImageDraw.Draw(hl).polygon([(s * .5, s * .04), (s * .08, s * .2), (s * .12, s * .58), (s * .5, s * .96)],
                               fill=(255, 255, 255, 26))
    out.alpha_composite(hl)
    ImageDraw.Draw(out).line(pts + [pts[0]], fill=(255, 255, 255, 90), width=3)
    d = ImageDraw.Draw(out)
    d.line([(s * .32, s * .5), (s * .46, s * .64), (s * .7, s * .36)],
           fill=(255, 255, 255, 255), width=max(6, s // 14), joint="curve")
    return out


def render(brand: str = config.BRAND, tagline: str = config.TAGLINE, path: str = OUT) -> str:
    rnd = random.Random(7)
    img = Image.new("RGBA", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)], fill=(int(7 + 6 * t), int(10 + 2 * t), int(26 + 18 * t), 255))

    # звёзды
    for _ in range(170):
        x, y = rnd.uniform(0, W), rnd.uniform(0, H)
        r = rnd.choice([0.6, 0.8, 1.0, 1.4])
        a = rnd.randint(60, 200)
        d.ellipse([x - r, y - r, x + r, y + r], fill=(220, 230, 255, a))

    # северное сияние: волна из размытых пятен
    colors = [(29, 233, 182), (41, 182, 246), (124, 77, 255), (224, 64, 251)]
    for i in range(26):
        t = i / 25
        cx = W * (0.25 + 0.85 * t)
        cy = H * (0.30 + 0.18 * math.sin(t * math.pi * 1.6))
        col = colors[min(3, int(t * 4))]
        glow(img, cx, cy, 160, 70, col, 95, 45)
    glow(img, W * 0.18, H * 0.52, 190, 190, (41, 182, 246), 55, 70)

    # щит со свечением
    sh = shield(300)
    halo = Image.new("RGBA", img.size, (0, 0, 0, 0))
    halo.paste(sh, (90, 170), sh)
    img.alpha_composite(halo.filter(ImageFilter.GaussianBlur(28)))
    img.alpha_composite(sh, (90, 170))

    # текст
    f_brand = find_font(["JetBrainsMono-ExtraBold.ttf", "DejaVuSans-Bold.ttf"], 104)
    f_tag = find_font(["Carlito-Regular.ttf", "DejaVuSans.ttf"], 42)
    f_chip = find_font(["JetBrainsMono-Bold.ttf", "DejaVuSans-Bold.ttf"], 24)
    x0 = 450
    size = 104
    while d.textlength(brand, font=f_brand) > W - x0 - 60 and size > 48:
        size -= 6
        f_brand = find_font(["JetBrainsMono-ExtraBold.ttf", "DejaVuSans-Bold.ttf"], size)

    txt = Image.new("RGBA", img.size, (0, 0, 0, 0))
    td = ImageDraw.Draw(txt)
    td.text((x0, 210), brand, font=f_brand, fill=(255, 255, 255, 255))
    img.alpha_composite(txt.filter(ImageFilter.GaussianBlur(14)))
    img.alpha_composite(txt)
    d = ImageDraw.Draw(img)
    d.text((x0 + 4, 345), tagline, font=f_tag, fill=(196, 206, 240, 255))

    # «чипы» под слоганом
    chips = Image.new("RGBA", img.size, (0, 0, 0, 0))
    cd = ImageDraw.Draw(chips)
    cx = x0 + 4
    for label in ("VLESS · REALITY", "БЕЗ ЛОГОВ", "24/7"):
        w = cd.textlength(label, font=f_chip) + 36
        cd.rounded_rectangle([cx, 420, cx + w, 468], radius=24,
                             fill=(120, 170, 255, 34), outline=(150, 200, 255, 120), width=2)
        cx += w + 14
    img.alpha_composite(chips)
    d = ImageDraw.Draw(img)
    cx = x0 + 4
    for label in ("VLESS · REALITY", "БЕЗ ЛОГОВ", "24/7"):
        w = d.textlength(label, font=f_chip) + 36
        d.text((cx + 18, 431), label, font=f_chip, fill=(225, 235, 255, 255))
        cx += w + 14

    # виньетка
    vig = Image.new("L", (W, H), 0)
    ImageDraw.Draw(vig).rectangle([0, 0, W, H], fill=255)
    vmask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(vmask).ellipse([-W * .15, -H * .35, W * 1.15, H * 1.35], fill=255)
    vmask = vmask.filter(ImageFilter.GaussianBlur(120))
    dark = Image.new("RGBA", (W, H), (3, 4, 12, 170))
    img = Image.composite(img, Image.alpha_composite(img, dark), vmask)

    img.convert("RGB").save(path, quality=95)
    return path


def ensure() -> str:
    if not os.path.exists(OUT):
        render()
    return OUT


if __name__ == "__main__":
    print("Баннер сохранён:", render())
