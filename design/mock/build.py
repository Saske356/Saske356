"""Собирает один HTML-файл макета (шрифт, глобус и знак внутри файла).

python3 design/mock/build.py  →  design/mock/arise-mock.html
"""
import base64, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "icons"))
import icons  # noqa: E402
import screens  # noqa: E402
ROOT = os.path.dirname(os.path.dirname(HERE))
FONT = os.path.join(ROOT, "arise-app/app/src/main/res/font")


def b64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


fonts = "".join(
    f"@font-face{{font-family:Inter;font-weight:{w};src:url(data:font/ttf;base64,{b64(os.path.join(FONT, f'inter_{n}.ttf'))}) format('truetype')}}"
    for n, w in (("regular", 400), ("medium", 500), ("semibold", 600), ("bold", 700))
)
html = open(os.path.join(HERE, "mock.template.html"), encoding="utf-8").read()
html = (html.replace("<!--SHEET-->", screens.sheet()).replace("<!--VIEWS-->", screens.views())
        .replace("/*SCREENS_CSS*/", screens.CSS).replace("//SCREENS_JS", screens.JS))
_n = [0]


GPT = os.path.join(os.path.dirname(HERE), "icons", "gpt")
_used = set()


def _ico(m):
    """Значок ChatGPT (design/icons/gpt/*.webp), если он есть, иначе свой глянцевый SVG."""
    _n[0] += 1
    name, px = m.group(1), m.group(2)
    # мелкие значки ChatGPT из-за толстого свечения расплываются в пятно — до 28 px свои
    if int(px) >= 28 and os.path.exists(os.path.join(GPT, name + ".webp")):
        _used.add(name)
        return f'<span class="ico gi-{name}" style="width:{px}px;height:{px}px"></span>'
    return f'<span class="ico" style="width:{px}px;height:{px}px">{icons.svg(name, "_" + str(_n[0]))}</span>'


html = re.sub(r"\{\{ico:(\w+):(\d+)\}\}", _ico, html)
gpt_css = "".join(f".gi-{n}{{background:url(data:image/webp;base64,{b64(os.path.join(GPT, n + '.webp'))}) center/contain no-repeat}}"
                  for n in sorted(_used))
html = html.replace("/*FONTS*/", "/*FONTS*/" + gpt_css)
html = (html.replace("/*FONTS*/", fonts)
        .replace("PHOTO_DATA", "data:image/jpeg;base64," + b64(os.path.join(HERE, "chat_photo.jpg")))
        .replace("GLOBE_DATA", "data:image/webp;base64," + b64(os.path.join(HERE, os.environ.get("GLOBE", "globe_gpt.webp"))))
        .replace("RING_DATA", "data:image/webp;base64," + b64(os.path.join(HERE, "ring_gpt.webp"))))
with open(os.path.join(HERE, "arise-mock.html"), "w", encoding="utf-8") as f:
    f.write(html)
print("ok", len(html) // 1024, "KB")
