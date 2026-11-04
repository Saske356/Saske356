"""Генерирует текстуру The Hollow (64x64) и иконки паков (128x128).
Запуск: python3 tools/make_textures.py  (из папки the-hollow)
"""
import random
from PIL import Image, ImageDraw, ImageFilter

random.seed(13)
W = H = 64
img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
px = img.load()


def skin(x0, y0, w, h, base=18, var=10):
    """Тёмная "кожа" с шумом."""
    for x in range(x0, x0 + w):
        for y in range(y0, y0 + h):
            v = base + random.randint(-var, var)
            px[x, y] = (v, v, v + 2, 255)


def box_area(u, v, w, h, d):
    """Вся область box-UV куба."""
    skin(u, v, 2 * (w + d), h + d)


def front(u, v, w, h, d):
    """Левый верхний угол передней (north) грани."""
    return u + d, v + d


# leg [3,26,3] uv(0,0) | body [10,16,5] uv(12,0) | arm [3,30,3] uv(42,0)
# horn [1,5,1] uv(54,0) | head [7,10,7] uv(0,36)
box_area(0, 0, 3, 26, 3)
box_area(12, 0, 10, 16, 5)
box_area(42, 0, 3, 30, 3)
box_area(0, 36, 7, 10, 7)
for x in range(54, 58):
    for y in range(0, 6):
        g = 150 + random.randint(-15, 15)
        px[x, y] = (g, g - 8, g - 25, 255)  # костяные рога

# Рёбра на груди
fx, fy = front(12, 0, 10, 16, 5)
for i, row in enumerate(range(fy + 3, fy + 11, 2)):
    for x in range(fx + 1, fx + 9):
        if x != fx + 4 and x != fx + 5:
            g = 70 - i * 6 + random.randint(-6, 6)
            px[x, row] = (g, g, g, 255)
# Трещина / дыра в животе
for y in range(fy + 11, fy + 15):
    for x in range(fx + 3, fx + 7):
        px[x, y] = (6, 0, 0, 255)

# Лицо: пустые белые глаза и длинный рот
hx, hy = front(0, 36, 7, 10, 7)
for x, y in [(hx + 1, hy + 3), (hx + 2, hy + 3), (hx + 4, hy + 3), (hx + 5, hy + 3)]:
    px[x, y] = (235, 235, 225, 255)
for x, y in [(hx + 1, hy + 4), (hx + 5, hy + 4)]:
    px[x, y] = (120, 120, 115, 255)  # "потёки" под глазами
for x in range(hx + 1, hx + 6):
    px[x, hy + 7] = (60, 0, 0, 255)
for x in (hx + 2, hx + 4):
    px[x, hy + 8] = (40, 0, 0, 255)

# Когти внизу рук: нижние 3 пикселя боковых граней + низ
for x in range(42, 54):
    for y in range(3 + 27, 3 + 30):
        g = 170 + random.randint(-20, 10)
        px[x, y] = (g, g - 10, g - 30, 255)

img.save("RP/textures/entity/the_hollow.png")


def icon(path, subtitle):
    im = Image.new("RGBA", (128, 128), (8, 8, 10, 255))
    d = ImageDraw.Draw(im)
    for _ in range(500):  # туман
        x, y = random.randint(0, 127), random.randint(60, 127)
        g = random.randint(20, 45)
        d.point((x, y), fill=(g, g, g, 255))
    # силуэт
    d.rectangle((58, 22, 70, 36), fill=(0, 0, 0, 255))   # голова
    d.rectangle((55, 36, 73, 70), fill=(0, 0, 0, 255))   # тело
    d.rectangle((49, 38, 54, 92), fill=(0, 0, 0, 255))   # руки
    d.rectangle((74, 38, 79, 92), fill=(0, 0, 0, 255))
    d.rectangle((57, 70, 62, 110), fill=(0, 0, 0, 255))  # ноги
    d.rectangle((66, 70, 71, 110), fill=(0, 0, 0, 255))
    d.line((60, 22, 57, 12), fill=(0, 0, 0, 255), width=2)  # рога
    d.line((68, 22, 71, 12), fill=(0, 0, 0, 255), width=2)
    im = im.filter(ImageFilter.GaussianBlur(0.6))
    d = ImageDraw.Draw(im)
    d.rectangle((60, 27, 61, 28), fill=(240, 240, 230, 255))  # глаза
    d.rectangle((66, 27, 67, 28), fill=(240, 240, 230, 255))
    d.text((6, 4), "THE HOLLOW", fill=(170, 170, 170, 255))
    d.text((6, 114), subtitle, fill=(110, 30, 30, 255))
    im.save(path)


icon("BP/pack_icon.png", "behavior")
icon("RP/pack_icon.png", "resources")
print("textures ok")
