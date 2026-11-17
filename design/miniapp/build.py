"""Собирает мини-приложение Telegram в один файл: docs/index.html (его раздаёт сервер подписок по /m/).

python3 design/miniapp/build.py

Внутрь файла вшиваются: шрифт Inter (woff2, только латиница и кириллица), Земля ChatGPT (уменьшенная),
значки — ChatGPT (design/icons/gpt) от 28 px, мельче — свои SVG (design/icons/icons.py). Нужны Pillow,
fonttools и brotli (pip install pillow fonttools brotli).
"""
import base64
import io
import os
import re
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "design", "icons"))
import icons  # noqa: E402

FONT = os.path.join(ROOT, "arise-app/app/src/main/res/font")
GPT = os.path.join(ROOT, "design", "icons", "gpt")
GLOBE = os.path.join(ROOT, "design", "mock", "globe_gpt.webp")
OUT = os.path.join(ROOT, "docs", "index.html")


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def woff2(path: str) -> bytes:
    from fontTools import subset
    from fontTools.ttLib import TTFont
    f = TTFont(path)
    opts = subset.Options()
    opts.flavor = "woff2"
    opts.layout_features = ["kern", "liga", "tnum", "lnum"]
    s = subset.Subsetter(opts)
    # латиница, кириллица, знаки препинания, ₽, стрелки
    s.populate(unicodes=list(range(0x20, 0x7F)) + list(range(0xA0, 0x100)) + list(range(0x400, 0x460)) +
               list(range(0x2010, 0x2030)) + [0x20BD, 0x2116, 0x2192, 0x2190, 0x2605, 0x25CF])
    s.subset(f)
    buf = io.BytesIO()
    f.flavor = "woff2"
    f.save(buf)
    return buf.getvalue()


def webp(path: str, px: int, q: int = 82) -> bytes:
    im = Image.open(path).convert("RGBA")
    im.thumbnail((px, px), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "WEBP", quality=q, method=6)
    return buf.getvalue()


fonts = "".join(
    f"@font-face{{font-family:Inter;font-weight:{w};font-display:swap;"
    f"src:url(data:font/woff2;base64,{b64(woff2(os.path.join(FONT, f'inter_{n}.ttf')))}) format('woff2')}}"
    for n, w in (("regular", 400), ("medium", 500), ("semibold", 600), ("bold", 700)))

html = open(os.path.join(HERE, "template.html"), encoding="utf-8").read()
_n = [0]
_used = set()


def _ico(m):
    _n[0] += 1
    name, px = m.group(1), m.group(2)
    if int(px) >= 28 and os.path.exists(os.path.join(GPT, name + ".webp")):
        _used.add(name)
        return f'<span class="ico gi-{name}" style="width:{px}px;height:{px}px"></span>'
    return f'<span class="ico" style="width:{px}px;height:{px}px">{icons.svg(name, "_" + str(_n[0]))}</span>'


html = re.sub(r"\{\{ico:(\w+):(\d+)\}\}", _ico, html)
gpt_css = "".join(f".gi-{n}{{background:url(data:image/webp;base64,{b64(webp(os.path.join(GPT, n + '.webp'), 96))}) center/contain no-repeat}}"
                  for n in sorted(_used))
earth = f":root{{--earth:url(data:image/webp;base64,{b64(webp(GLOBE, 720, 78))})}}"
html = html.replace("/*FONTS*/", fonts + gpt_css + earth)
with open(OUT, "w", encoding="utf-8") as f:
    f.write(html)
print("ok", OUT, len(html) // 1024, "KB")
