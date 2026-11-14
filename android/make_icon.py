"""Иконка приложения из эмблемы бота (щит с «A», чёрный + синий): python3 make_icon.py <res-папка>."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "vpn-bot"))
from PIL import Image, ImageDraw, ImageFilter  # noqa: E402

import make_banner  # noqa: E402

BG = (3, 5, 11, 255)
# плотность -> (обычная иконка, слой переднего плана адаптивной иконки)
SIZES = {"mdpi": (48, 108), "hdpi": (72, 162), "xhdpi": (96, 216), "xxhdpi": (144, 324), "xxxhdpi": (192, 432)}


def foreground(size: int) -> Image.Image:
    # Видимая часть адаптивной иконки — круг 66 из 108: эмблема занимает чуть меньше.
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    em = make_banner.emblem(int(size * 0.56), "A")
    img.alpha_composite(em, ((size - em.width) // 2, (size - em.height) // 2 + size // 90))
    return img


def legacy(size: int, round_: bool) -> Image.Image:
    big = 512
    img = Image.new("RGBA", (big, big), BG)
    glow = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([30, 170, big - 30, big + 120], fill=(24, 72, 190, 200))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(70)))
    em = make_banner.emblem(int(big * 0.74), "A")
    img.alpha_composite(em, ((big - em.width) // 2, (big - em.height) // 2 + 4))
    mask = Image.new("L", (big, big), 0)
    d = ImageDraw.Draw(mask)
    if round_:
        d.ellipse([0, 0, big - 1, big - 1], fill=255)
    else:
        d.rounded_rectangle([0, 0, big - 1, big - 1], radius=big // 6, fill=255)
    out = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    out.paste(img, mask=mask)
    return out.resize((size, size), Image.LANCZOS)


def main(res: str) -> None:
    for dpi, (icon, fg) in SIZES.items():
        d = os.path.join(res, f"mipmap-{dpi}")
        os.makedirs(d, exist_ok=True)
        legacy(icon, False).save(os.path.join(d, "ic_launcher.png"))
        legacy(icon, True).save(os.path.join(d, "ic_launcher_round.png"))
        foreground(fg).save(os.path.join(d, "ic_launcher_foreground.png"))
    with open(os.path.join(res, "values", "ic_launcher_background.xml"), "w") as f:
        f.write('<?xml version="1.0" encoding="utf-8"?>\n<resources>\n'
                '    <color name="ic_launcher_background">#03050B</color>\n</resources>\n')


if __name__ == "__main__":
    main(sys.argv[1])
