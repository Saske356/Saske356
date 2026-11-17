"""Значок Arise: буква «A» со стрелкой вверх (по образцу design/gpt/07-logo.png).

Форма — один многоугольник, поэтому значок рисуется здесь заново в нужных размерах, чётко,
а не нарезается из картинки нейросети. Запуск: python3 arise-app/design/make_logo.py
"""
import os
from PIL import Image, ImageDraw, ImageFilter

# Вершины в координатах образца 1254×1254 (обход по контуру)
RAW = [(628, 265), (1038, 937), (713, 815), (683, 704), (776, 741), (628, 515),
       (480, 741), (573, 704), (543, 815), (218, 937)]
X0, X1, Y0, Y1 = 218, 1038, 265, 937

TOP, BOTTOM = (232, 244, 255), (37, 99, 255)        # градиент знака сверху вниз
BG_TOP, BG_BOTTOM = (13, 28, 62), (2, 4, 11)        # фон
GLOW = (47, 107, 255)

RES = os.path.join(os.path.dirname(__file__), "..", "app", "src", "main", "res")
DENS = {"mdpi": 1, "hdpi": 1.5, "xhdpi": 2, "xxhdpi": 3, "xxxhdpi": 4}


def points(size, scale):
    """Знак по центру квадрата size, ширина знака = scale·size."""
    w = scale * size
    k = w / (X1 - X0)
    h = (Y1 - Y0) * k
    ox, oy = (size - w) / 2, (size - h) / 2 + h * 0.02
    return [(ox + (x - X0) * k, oy + (y - Y0) * k) for x, y in RAW]


def vgrad(size, top, bottom):
    g = Image.new("RGB", (1, size))
    for y in range(size):
        t = y / max(1, size - 1)
        g.putpixel((0, y), tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)))
    return g.resize((size, size))


def mark(size, scale, glow=True):
    """Прозрачный слой: свечение + знак с градиентом."""
    s = size * 4  # рисуем крупнее и уменьшаем — ровные края
    pts = points(s, scale)
    layer = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    if glow:
        m = Image.new("L", (s, s), 0)
        ImageDraw.Draw(m).polygon(pts, fill=255)
        m = m.filter(ImageFilter.GaussianBlur(s * 0.035))
        g = Image.new("RGBA", (s, s), GLOW + (0,))
        g.putalpha(m.point(lambda v: int(v * 0.85)))
        layer = Image.alpha_composite(layer, g)
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).polygon(pts, fill=255)
    fill = vgrad(s, TOP, BOTTOM).convert("RGBA")
    fill.putalpha(mask)
    layer = Image.alpha_composite(layer, fill)
    return layer.resize((size, size), Image.LANCZOS)


def full(size, scale, shape):
    bg = vgrad(size, BG_TOP, BG_BOTTOM).convert("RGBA")
    img = Image.alpha_composite(bg, mark(size, scale))
    m = Image.new("L", (size * 4, size * 4), 0)
    d = ImageDraw.Draw(m)
    if shape == "round":
        d.ellipse((0, 0, size * 4 - 1, size * 4 - 1), fill=255)
    else:
        d.rounded_rectangle((0, 0, size * 4 - 1, size * 4 - 1), radius=size * 4 * 0.22, fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(img, (0, 0), m.resize((size, size), Image.LANCZOS))
    return out


def main():
    for d, k in DENS.items():
        folder = os.path.join(RES, f"mipmap-{d}")
        full(int(48 * k), 0.62, "square").save(os.path.join(folder, "ic_launcher.png"))
        full(int(48 * k), 0.58, "round").save(os.path.join(folder, "ic_launcher_round.png"))
        # адаптивный значок: 108 dp, видимая зона ~66 dp — знак около 40% ширины слоя
        mark(int(108 * k), 0.40).save(os.path.join(folder, "ic_launcher_foreground.png"))
    # Аватарка бота и крупный образец
    out = os.path.join(os.path.dirname(__file__), "logo-1024.png")
    full(1024, 0.6, "square").convert("RGB").save(out)
    full(640, 0.56, "round").save(os.path.join(os.path.dirname(__file__), "avatar-640.png"))
    # Контур для одноцветных значков (уведомление, плитка в шторке): viewport 24×24
    pts = points(24, 0.86)
    print("M" + "L".join(f"{x:.2f},{y:.2f}" for x, y in pts) + "Z")


if __name__ == "__main__":
    main()
