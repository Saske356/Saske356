"""Премиальные баннеры бота (чёрный + золото) и аватарка.

python make_banner.py  — перерисовать все баннеры после смены BRAND/TAGLINE.
"""

import math
import os
import random

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

import config

W, H = 1280, 640
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "banners")

# раздел -> (крупная надпись, мелкая надпись над ней). None = название бренда.
SECTIONS = {
    "main": (None, "PRIVATE  ACCESS"),
    "plans": ("ТАРИФЫ", None),
    "key": ("ВАШ КЛЮЧ", None),
    "howto": ("ПОДКЛЮЧЕНИЕ", None),
    "profile": ("ПРОФИЛЬ", None),
    "ref": ("ПРИВИЛЕГИИ", None),
    "support": ("КОНСЬЕРЖ", None),
    "welcome": ("ДОБРО ПОЖАЛОВАТЬ", None),
}

FONT_DIRS = ["/usr/share/fonts/truetype", "/system/fonts",
             "/data/data/com.termux/files/usr/share/fonts", HERE]
SERIF = ["Caladea-Bold.ttf", "LiberationSerif-Bold.ttf", "DejaVuSerif-Bold.ttf", "DejaVuSans-Bold.ttf"]
SERIF_CYR = ["LiberationSerif-Bold.ttf", "FreeSerifBold.ttf", "DejaVuSerif-Bold.ttf", "DejaVuSans-Bold.ttf"]
SANS = ["Carlito-Regular.ttf", "LiberationSans-Regular.ttf", "DejaVuSans.ttf"]


def font(names, size):
    for n in names:
        for d in FONT_DIRS:
            for root, _, files in os.walk(d):
                if n in files:
                    return ImageFont.truetype(os.path.join(root, n), size)
    return ImageFont.load_default(size)


def serif_for(text):
    """Caladea красивее, но без кириллицы: для русского текста берём другой шрифт."""
    return SERIF_CYR if any("\u0400" <= ch <= "\u04ff" for ch in text) else SERIF


def gold_fill(size):
    """Металлический золотой градиент с бликом."""
    w, h = size
    g = Image.new("RGBA", size)
    d = ImageDraw.Draw(g)
    stops = [(0.0, (255, 241, 196)), (0.32, (232, 196, 108)), (0.55, (176, 129, 42)),
             (0.72, (222, 182, 92)), (1.0, (255, 232, 168))]
    for y in range(h):
        t = y / max(1, h - 1)
        for i in range(len(stops) - 1):
            a, b = stops[i], stops[i + 1]
            if a[0] <= t <= b[0]:
                k = (t - a[0]) / (b[0] - a[0])
                c = tuple(int(a[1][j] + (b[1][j] - a[1][j]) * k) for j in range(3))
                break
        d.line([(0, y), (w, y)], fill=c + (255,))
    return g


def spaced_width(text, f, spacing):
    return sum(f.getlength(ch) for ch in text) + spacing * (len(text) - 1)


def draw_spaced(draw, x, y, text, f, spacing, fill):
    for ch in text:
        draw.text((x, y), ch, font=f, fill=fill)
        x += f.getlength(ch) + spacing


def gold_text(img, x, y, text, f, spacing, glow=True):
    """Рисует текст золотом с лёгким свечением."""
    mask = Image.new("L", img.size, 0)
    draw_spaced(ImageDraw.Draw(mask), x, y, text, f, spacing, 255)
    if glow:
        halo = Image.new("RGBA", img.size, (214, 170, 80, 0))
        halo.putalpha(mask.filter(ImageFilter.GaussianBlur(16)).point(lambda v: int(v * 0.45)))
        img.alpha_composite(halo)
    bbox = mask.getbbox()
    if not bbox:
        return
    fill = Image.new("RGBA", img.size, (0, 0, 0, 0))
    fill.paste(gold_fill((bbox[2] - bbox[0], bbox[3] - bbox[1])), bbox[:2])
    fill.putalpha(ImageChops.multiply(fill.getchannel("A"), mask))
    img.alpha_composite(fill)


def emblem(size, letter):
    """Золотой щит с чёрной вставкой и монограммой."""
    s = size
    def shield(scale):
        m = (1 - scale) / 2
        return [(s * (m + scale * x), s * (m + scale * y)) for x, y in
                [(.5, .03), (.93, .18), (.89, .56), (.5, .97), (.11, .56), (.07, .18)]]
    out = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    outer = Image.new("L", (s, s), 0)
    ImageDraw.Draw(outer).polygon(shield(1.0), fill=255)
    g = gold_fill((s, s))
    g.putalpha(outer)
    out.alpha_composite(g)
    inner = Image.new("L", (s, s), 0)
    ImageDraw.Draw(inner).polygon(shield(0.84), fill=255)
    black = Image.new("RGBA", (s, s), (12, 10, 9, 255))
    black.putalpha(inner)
    out.alpha_composite(black)
    line = Image.new("L", (s, s), 0)
    ImageDraw.Draw(line).polygon(shield(0.76), outline=255, width=max(2, s // 120))
    gl = gold_fill((s, s))
    gl.putalpha(line.point(lambda v: int(v * 0.8)))
    out.alpha_composite(gl)
    f = font(serif_for(letter), int(s * 0.46))
    bb = f.getbbox(letter)
    lx = (s - (bb[2] - bb[0])) / 2 - bb[0]
    ly = s * 0.47 - (bb[3] - bb[1]) / 2 - bb[1]
    gold_text(out, lx, ly, letter, f, 0, glow=False)
    return out


def base(seed=11):
    rnd = random.Random(seed)
    img = Image.new("RGBA", (W, H), (7, 6, 9, 255))
    # тёплое свечение из центра
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([W * .05, H * .05, W * .95, H * 1.2], fill=(70, 48, 18, 120))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(160)))
    # золотое боке
    bok = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bd = ImageDraw.Draw(bok)
    for _ in range(46):
        x, y, r = rnd.uniform(0, W), rnd.uniform(0, H), rnd.uniform(2, 14)
        bd.ellipse([x - r, y - r, x + r, y + r], fill=(232, 190, 100, rnd.randint(14, 50)))
    img.alpha_composite(bok.filter(ImageFilter.GaussianBlur(3)))
    # тонкие диагональные лучи
    rays = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    rd = ImageDraw.Draw(rays)
    for i in range(7):
        x = W * (0.48 + i * 0.075)
        rd.line([(x, -20), (x - 380, H + 20)], fill=(240, 205, 130, 10 + i * 2), width=2)
    img.alpha_composite(rays.filter(ImageFilter.GaussianBlur(1)))
    # рамка ар-деко
    frame = Image.new("L", (W, H), 0)
    fd = ImageDraw.Draw(frame)
    fd.rectangle([26, 26, W - 27, H - 27], outline=150, width=2)
    fd.rectangle([36, 36, W - 37, H - 37], outline=70, width=1)
    for cx, cy in [(26, 26), (W - 27, 26), (26, H - 27), (W - 27, H - 27)]:
        fd.polygon([(cx, cy - 11), (cx + 11, cy), (cx, cy + 11), (cx - 11, cy)], fill=230)
    gf = gold_fill((W, H))
    gf.putalpha(frame)
    img.alpha_composite(gf)
    return img


def render(section="main", path=None):
    big, small = SECTIONS[section]
    brand = config.BRAND.upper()
    img = base()
    d = ImageDraw.Draw(img)

    em = emblem(290, brand[:1])
    halo = Image.new("RGBA", img.size, (0, 0, 0, 0))
    halo.paste(em, (110, 175), em)
    shadow = Image.new("RGBA", img.size, (230, 180, 80, 0))
    shadow.putalpha(halo.getchannel("A").filter(ImageFilter.GaussianBlur(30)).point(lambda v: int(v * .5)))
    img.alpha_composite(shadow)
    img.alpha_composite(em, (110, 175))

    x0, max_w = 470, W - 470 - 80
    headline = brand if big is None else big
    small = small if small is not None else brand
    size = 110
    face = serif_for(headline)
    f_big = font(face, size)
    sp = 10
    while spaced_width(headline, f_big, sp) > max_w and size > 46:
        size -= 4
        sp = max(3, size // 11)
        f_big = font(face, size)
    f_small = font(SANS, 27)
    # мелкая надпись, линия, крупная надпись, подпись
    gold_text(img, x0 + 4, 236 - (110 - size) // 3, small, f_small, 9, glow=False)
    gold_text(img, x0, 272 - (110 - size) // 3, headline, f_big, sp)
    ly = 410
    line = Image.new("L", img.size, 0)
    ImageDraw.Draw(line).line([(x0 + 4, ly), (x0 + 250, ly)], fill=200, width=2)
    ImageDraw.Draw(line).polygon([(x0 + 262, ly - 6), (x0 + 268, ly), (x0 + 262, ly + 6), (x0 + 256, ly)], fill=230)
    gl = gold_fill(img.size)
    gl.putalpha(line)
    img.alpha_composite(gl)
    tag = config.TAGLINE if section == "main" else "PRIVATE  ACCESS  ·  " + brand
    f_tag = font(SANS, 30 if section == "main" else 22)
    sp_tag = 1 if section == "main" else 6
    d.text((x0 + 4, 432), "", font=f_tag)
    draw_spaced(ImageDraw.Draw(img), x0 + 4, 432, tag, f_tag, sp_tag, (214, 200, 170, 255))

    path = path or os.path.join(OUT_DIR, f"{section}.jpg")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.convert("RGB").save(path, quality=93)
    return path


def render_avatar(path=None):
    s = 640
    img = Image.new("RGBA", (s, s), (7, 6, 9, 255))
    glow = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([60, 60, s - 60, s - 60], fill=(90, 62, 20, 150))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(90)))
    em = emblem(400, config.BRAND[:1].upper())
    img.alpha_composite(em, ((s - 400) // 2, (s - 400) // 2 + 6))
    path = path or os.path.join(OUT_DIR, "avatar.jpg")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.convert("RGB").save(path, quality=95)
    return path


def ensure() -> dict:
    """Пути ко всем баннерам; недостающие дорисовывает."""
    paths = {}
    for name in SECTIONS:
        p = os.path.join(OUT_DIR, f"{name}.jpg")
        if not os.path.exists(p):
            render(name, p)
        paths[name] = p
    return paths


if __name__ == "__main__":
    for name in SECTIONS:
        print("баннер:", render(name))
    print("аватарка:", render_avatar())
