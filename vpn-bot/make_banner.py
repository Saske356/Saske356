"""Баннеры бота и аватарка — в стиле приложения Arise.

Тёмный космос со звёздами, справа светится Земля (та же картинка, что на главном экране
приложения), слева знак Arise («A» со стрелкой вверх), крупная надпись раздела шрифтом Inter
и подпись. Шрифт Inter (SIL OFL) и Земля лежат в assets/.

python make_banner.py  — перерисовать все баннеры после смены BRAND/TAGLINE.
"""

import os
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont

import config

W, H = 1280, 640
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "banners")
ASSETS = os.path.join(HERE, "assets")

# раздел -> (крупная надпись, мелкая надпись над ней). None = название бренда.
SECTIONS = {
    "main": (None, "PRIVATE  ACCESS"),
    "plans": ("ТАРИФЫ", None),
    "key": ("ВАШ КЛЮЧ", None),
    "howto": ("ПОДКЛЮЧЕНИЕ", None),
    "profile": ("ПРОФИЛЬ", None),
    "ref": ("ПРИВИЛЕГИИ", None),
    "support": ("ПОДДЕРЖКА", None),
    "welcome": ("ДОБРО ПОЖАЛОВАТЬ", None),
}

BG = (2, 5, 15)
TEXT_SOFT = (176, 196, 232)
BLUE = (79, 141, 255)

# знак Arise: «A» со стрелкой вверх (как в приложении), координаты образца 1254×1254
MARK = [(628, 265), (1038, 937), (713, 815), (683, 704), (776, 741), (628, 515),
        (480, 741), (573, 704), (543, 815), (218, 937)]


def font(weight, size):
    path = os.path.join(ASSETS, f"inter_{weight}.ttf")
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default(size)


def vgrad(w, h, top, bottom):
    g = Image.new("RGBA", (1, h))
    for y in range(h):
        t = y / max(1, h - 1)
        g.putpixel((0, y), tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)) + (255,))
    return g.resize((w, h))


def mark(size):
    """Знак со свечением, прозрачный фон."""
    s = size * 3
    k = s * 0.86 / (1038 - 218)
    ox = (s - (1038 - 218) * k) / 2
    oy = (s - (937 - 265) * k) / 2
    pts = [(ox + (x - 218) * k, oy + (y - 265) * k) for x, y in MARK]
    m = Image.new("L", (s, s), 0)
    ImageDraw.Draw(m).polygon(pts, fill=255)
    out = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    glow = Image.new("RGBA", (s, s), (47, 107, 255, 0))
    glow.putalpha(m.filter(ImageFilter.GaussianBlur(s * 0.05)).point(lambda v: int(v * 0.9)))
    out.alpha_composite(glow)
    fill = vgrad(s, s, (234, 245, 255), (37, 99, 255))
    fill.putalpha(m)
    out.alpha_composite(fill)
    return out.resize((size, size), Image.LANCZOS)


def gradient_text(img, xy, text, f, top=(255, 255, 255), bottom=(140, 185, 255), glow=True, spacing=0):
    """Текст с вертикальным градиентом и синим свечением."""
    m = Image.new("L", img.size, 0)
    d = ImageDraw.Draw(m)
    x, y = xy
    if spacing:
        for ch in text:
            d.text((x, y), ch, font=f, fill=255)
            x += f.getlength(ch) + spacing
    else:
        d.text((x, y), text, font=f, fill=255)
    bbox = m.getbbox()
    if not bbox:
        return
    if glow:
        g = Image.new("RGBA", img.size, (60, 120, 255, 0))
        g.putalpha(m.filter(ImageFilter.GaussianBlur(14)).point(lambda v: int(v * 0.7)))
        img.alpha_composite(g)
    fill = Image.new("RGBA", img.size, (0, 0, 0, 0))
    fill.paste(vgrad(bbox[2] - bbox[0], bbox[3] - bbox[1], top, bottom), bbox[:2])
    fill.putalpha(m)
    img.alpha_composite(fill)


def spaced_width(text, f, spacing):
    return sum(f.getlength(ch) for ch in text) + spacing * max(0, len(text) - 1)


def base(seed=11):
    rnd = random.Random(seed)
    img = Image.new("RGBA", (W, H), BG + (255,))
    # мягкое синее сияние из-за Земли
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([560, -60, 1460, 760], fill=(30, 80, 220, 120))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(120)))
    # звёзды
    st = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(st)
    for _ in range(170):
        x, y = rnd.uniform(0, W), rnd.uniform(0, H)
        r = rnd.choice((0.6, 0.8, 1.0, 1.2, 1.6))
        sd.ellipse([x - r, y - r, x + r, y + r], fill=(205, 225, 255, rnd.randint(60, 220)))
    img.alpha_composite(st)
    # Земля справа, частично за краем
    try:
        globe = Image.open(os.path.join(ASSETS, "globe.webp")).convert("RGBA").resize((860, 860), Image.LANCZOS)
        img.alpha_composite(globe, (700, -110))
    except OSError:
        pass
    # затемнение слева, чтобы текст читался
    shade = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sh = ImageDraw.Draw(shade)
    for x in range(W):
        a = int(235 * max(0.0, min(1.0, (860 - x) / 420)))
        sh.line([(x, 0), (x, H)], fill=BG + (a,))
    img.alpha_composite(shade)
    # светящиеся дуги в нижних углах
    arcs = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ad = ImageDraw.Draw(arcs)
    ad.ellipse([-520, 520, 620, 1180], outline=(80, 140, 255, 200), width=4)
    ad.ellipse([660, 540, 1800, 1200], outline=(80, 140, 255, 160), width=3)
    img.alpha_composite(arcs.filter(ImageFilter.GaussianBlur(3)))
    img.alpha_composite(arcs.filter(ImageFilter.GaussianBlur(22)))
    return img


def render(section="main", path=None):
    big, small = SECTIONS[section]
    brand = config.BRAND.upper()
    img = base()
    x0 = 92
    m = mark(132)
    img.alpha_composite(m, (x0 - 14, 118))
    small = small if small is not None else brand
    f_small = font("semibold", 26)
    gradient_text(img, (x0 + 140, 160), small, f_small, (200, 220, 255), (140, 180, 250), glow=False, spacing=7)
    headline = brand if big is None else big
    size = 104
    f_big = font("bold", size)
    while spaced_width(headline, f_big, 2) > 680 and size > 46:
        size -= 4
        f_big = font("bold", size)
    gradient_text(img, (x0, 290), headline, f_big, spacing=2)
    # линия с огоньком
    ly = 290 + size + 34
    line = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ld = ImageDraw.Draw(line)
    ld.line([(x0 + 2, ly), (x0 + 300, ly)], fill=BLUE + (230,), width=3)
    ld.ellipse([x0 + 296, ly - 6, x0 + 308, ly + 6], fill=(230, 242, 255, 255))
    img.alpha_composite(line.filter(ImageFilter.GaussianBlur(5)))
    img.alpha_composite(line)
    tag = config.TAGLINE if section == "main" else "Arise VPN · быстрый и приватный интернет"
    ImageDraw.Draw(img).text((x0 + 2, ly + 26), tag, font=font("regular", 30), fill=TEXT_SOFT + (255,))

    path = path or os.path.join(OUT_DIR, f"{section}.jpg")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.convert("RGB").save(path, quality=93)
    return path


def render_avatar(path=None):
    """Аватарка: знак на тёмно-синем, по центру — Telegram обрежет в круг."""
    s = 640
    img = vgrad(s, s, (13, 28, 62), (2, 4, 11))
    glow = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([120, 140, s - 120, s - 100], fill=(47, 107, 255, 150))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(80)))
    m = mark(400)
    img.alpha_composite(m, ((s - 400) // 2, (s - 400) // 2 + 8))
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
