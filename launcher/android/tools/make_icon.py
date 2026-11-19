"""Рисует иконку лаунчера во всех плотностях: res/mipmap-*/ic_launcher.png."""
import os, sys
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIZES = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

def draw(n):
    s = 4 * n  # рисуем крупно и уменьшаем — так края гладкие
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    r = s * 0.22
    d.rounded_rectangle([0, 0, s - 1, s - 1], r, fill=(22, 26, 34, 255))
    # силуэт города
    import random
    rnd = random.Random(7)
    x = s * 0.08
    while x < s * 0.92:
        w = s * rnd.uniform(0.08, 0.14)
        h = s * rnd.uniform(0.18, 0.42)
        d.rectangle([x, s * 0.78 - h, x + w, s * 0.78], fill=(48, 56, 72, 255))
        x += w + s * 0.015
    d.rectangle([s * 0.08, s * 0.78, s * 0.92, s * 0.82], fill=(255, 138, 61, 255))
    try:
        f = ImageFont.truetype(FONT, int(s * 0.42))
    except OSError:
        f = ImageFont.load_default()
    d.text((s / 2, s * 0.3), "Н", font=f, fill=(255, 138, 61, 255), anchor="mm",
           stroke_width=int(s * 0.02), stroke_fill=(22, 26, 34, 255))
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, s - 1, s - 1], r, fill=255)
    im.putalpha(mask)
    return im.resize((n, n), Image.LANCZOS)

for name, n in SIZES.items():
    out = os.path.join(ROOT, "res", f"mipmap-{name}")
    os.makedirs(out, exist_ok=True)
    draw(n).save(os.path.join(out, "ic_launcher.png"))
draw(512).save(os.path.join(ROOT, "icon-512.png"))
print("ok")
